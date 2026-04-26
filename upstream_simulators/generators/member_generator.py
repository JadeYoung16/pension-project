"""
Member Generator — Stage 2

Generates the ONCAP monthly member census in fixed-width format, one member
per record. Fields follow member_census_layout.yaml (400-char records, HDR
+ 50,000 detail + TRL).

Output:
  - ONCAP001_MEMBER_CENSUS_20240131.DAT  (current snapshot)
  - ONCAP001_MEMBER_CENSUS_20231231.DAT  (previous month snapshot, for diff)

Business rules (from docs/01_plan_design_specification.md):
  - 50,000 total members
  - Status: 55% Active, 20% Deferred, 15% Retired, 8% Terminated, 2% Survivor
  - Each member belongs to exactly one employer (partitioned by enrolled_member_count)
  - Age distribution varies by status (active 22-65, retired 55-95, etc.)
  - Salary: Active/Deferred only; by salary band (Entry/Mid/Senior/Executive)
  - Credited service ≤ plan age (10 years)
  - Buyback eligibility: 30% of Active, 15% of Deferred

Messiness injection (from messiness_config.yaml):
  - 15% email missing (35% for members 60+)
  - 60% no middle initial
  - 3% marital_status=U, 2% sex_code=9, 8% phone missing
  - 5% trailing whitespace in name
  - 1% non-ASCII name (French accent)

Usage:
  python -m upstream_simulators.generators.member_generator
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml

from upstream_simulators.shared.dates import (
    add_years, age_at, dob_from_age, random_date_between,
)
from upstream_simulators.shared.faker_pool import get_multilingual_faker
from upstream_simulators.shared.ids import generate_member_id, generate_sin_last_4
from upstream_simulators.shared.messiness import (
    maybe_add_accents, maybe_add_trailing_whitespace, maybe_null, roll,
)
from upstream_simulators.shared.writers.fixed_width import (
    FixedWidthLayout, FixedWidthWriter,
)


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("member_generator")


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_EMPLOYER_CSV = PROJECT_ROOT / "data" / "synthetic" / "employer_registry" / "ONCAP001_EMPLOYER_REGISTRY_20240131.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "member_census"


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass
class EmployerInfo:
    """Minimal employer attributes needed for member generation."""
    employer_id: str
    legal_name: str
    operating_name: str
    city: str
    enrolled_member_count: int
    participation_start_date: date


@dataclass
class MemberGenStats:
    """Statistics accumulator for the generation run."""
    total_members: int = 0
    per_status: dict[str, int] = field(default_factory=dict)
    per_salary_band: dict[str, int] = field(default_factory=dict)
    per_sex: dict[str, int] = field(default_factory=dict)
    buyback_eligible_count: int = 0
    email_missing_count: int = 0
    non_ascii_name_count: int = 0
    sum_annual_salary: float = 0.0
    sum_accrued_pension: float = 0.0


# -----------------------------------------------------------------------------
# Config loading
# -----------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_employers(csv_path: Path) -> list[EmployerInfo]:
    """Read employer registry CSV. Use csv.DictReader to handle quoted fields."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Employer registry not found: {csv_path}\n"
            "Run employer_generator first."
        )
    employers = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            employers.append(EmployerInfo(
                employer_id=row["employer_id"],
                legal_name=row["legal_name"],
                operating_name=row["operating_name"],
                city=row["city"],
                enrolled_member_count=int(row["enrolled_member_count"]),
                participation_start_date=date.fromisoformat(
                    row["participation_start_date"]
                ),
            ))
    return employers


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------

def weighted_choice(choices: dict, rng: random.Random):
    """Pick a key from {value: weight}."""
    items = list(choices.items())
    keys = [k for k, _ in items]
    weights = [w for _, w in items]
    return rng.choices(keys, weights=weights, k=1)[0]


def pick_salary_band(config: dict, rng: random.Random) -> dict:
    """Return a full salary band dict from config."""
    bands = config["members"]["salary_bands"]
    weights = [b["weight"] for b in bands]
    return rng.choices(bands, weights=weights, k=1)[0]


def pick_age_for_status(config: dict, status: str, rng: random.Random) -> int:
    """Pick a realistic age given member status.

    Uses a triangular distribution: biased toward the median age for that
    status, bounded by min/max.
    """
    lo, hi, median = config["members"]["age_by_status"][status]
    # triangular(low, high, mode)
    return int(rng.triangular(lo, hi, median))


def pick_service_years_for_active(
    enrollment_date: date, as_of: date
) -> float:
    """Credited service years, capped at plan age (10 years)."""
    days = (as_of - enrollment_date).days
    years = days / 365.25
    return max(0.0, min(10.0, years))


def pick_enrollment_date(
    plan_start: date,
    employer_start: date,
    as_of: date,
    hire_date: date,
    rng: random.Random,
) -> date:
    """
    Enrollment must be ≥ plan_start AND ≥ employer_start AND ≥ hire_date.
    Waiting period after hire: 0-90 days (we use 30 days average).
    """
    earliest = max(plan_start, employer_start, hire_date)
    if earliest >= as_of:
        earliest = as_of - timedelta(days=30)
    # Waiting period: between 0-90 days after hire (truncated at earliest)
    waiting_days = rng.randint(0, 90)
    candidate = hire_date + timedelta(days=waiting_days)
    return max(earliest, min(candidate, as_of - timedelta(days=1)))


def pick_hire_date(
    dob: date, employer_start: date, as_of: date, rng: random.Random
) -> date:
    """
    Hire date must be after age 18, after employer existed, before as_of.
    Uniform random in valid range.
    """
    min_hire = max(
        add_years(dob, 18),  # can't hire before age 18
        date(2000, 1, 1),     # don't go too far back
    )
    max_hire = as_of - timedelta(days=1)
    if min_hire >= max_hire:
        return max_hire
    return random_date_between(min_hire, max_hire, rng)


def compute_salary(status: str, band: dict, rng: random.Random) -> float:
    """Salary only for Active/Deferred; 0 otherwise. Uniform within band range."""
    if status not in ("A", "D"):
        return 0.0
    lo, hi = band["range"]
    return round(rng.uniform(lo, hi), 2)


def compute_accrued_pension(
    salary: float, service_years: float, accrual_rate: float
) -> float:
    """
    Annual pension = salary × accrual_rate × service_years.
    For retired members, we use a flat calculation based on stored history.
    """
    if salary == 0 or service_years == 0:
        return 0.0
    return round(salary * accrual_rate * service_years, 2)


def compute_accrued_pension_retired(
    age: int, rng: random.Random
) -> float:
    """For retirees, generate a plausible accrued pension amount."""
    # Most retirees get $8k-$45k/year from OPTrust Select-style DB plan
    return round(rng.uniform(8_000, 45_000), 2)


def make_synthetic_sin() -> str:
    """
    Placeholder SIN — the actual value isn't used anywhere. Full SIN is NEVER
    in the file; only last 4 digits go in SIN_LAST_4 field.
    """
    return "000000000"


def make_email(first_name: str, last_name: str, employer_op_name: str) -> str:
    """Synthesize a member email in a generic format."""
    first_clean = "".join(c for c in first_name.lower() if c.isalpha())[:15]
    last_clean = "".join(c for c in last_name.lower() if c.isalpha())[:20]
    # Simple generic domain pool
    domains = ["gmail.com", "hotmail.com", "yahoo.ca", "outlook.com"]
    return f"{first_clean}.{last_clean}@{random.choice(domains)}"  # nosec


def make_phone(rng: random.Random) -> str:
    """Generate a 10-digit phone number as a 10-char string."""
    # Ontario area codes
    area = rng.choice(["416", "647", "437", "613", "343", "905", "289", "519", "226"])
    exchange = rng.randint(200, 999)
    line = rng.randint(1000, 9999)
    return f"{area}{exchange}{line:04d}"


def make_street_address(fake) -> str:
    """Single-line street address (no line breaks)."""
    street = fake.street_address()
    # Replace any newlines with spaces (faker sometimes includes apartment lines)
    return " ".join(street.split())[:40]


def compute_member_to_employer_mapping(
    employers: list[EmployerInfo],
) -> list[tuple[int, EmployerInfo]]:
    """
    Return a flat list where element i = (sequence_in_employer, EmployerInfo)
    for member at global index i. Length = sum(enrolled_member_count).

    This guarantees:
      - Each member deterministically mapped to one employer
      - Employer member counts match exactly
    """
    mapping = []
    for emp in employers:
        for seq in range(emp.enrolled_member_count):
            mapping.append((seq, emp))
    return mapping


# -----------------------------------------------------------------------------
# Core member record builder
# -----------------------------------------------------------------------------

def build_member_record(
    member_id: str,
    employer: EmployerInfo,
    config: dict,
    messiness: dict,
    as_of: date,
    plan_start: date,
    rng: random.Random,
    fake,
) -> dict:
    """
    Build a single member record dict suitable for passing to the
    fixed-width writer. Returns dict keyed by field names from the layout.
    """
    mc = messiness["member_census"]
    mcfg = config["members"]

    # --- Status ---
    status = weighted_choice(mcfg["status_distribution"], rng)

    # --- Age / DOB ---
    age = pick_age_for_status(config, status, rng)
    dob = dob_from_age(age, as_of, rng)

    # --- Sex ---
    sex = weighted_choice(mcfg["sex_distribution"], rng)
    # Apply messiness: 2% become '9' unknown
    if roll(mc["sex_unknown"], rng):
        sex = "9"

    # --- Name (from Faker, optionally with accents) ---
    if sex == "1":
        first_name = fake["en_CA"].first_name_male()
    elif sex == "2":
        first_name = fake["en_CA"].first_name_female()
    else:
        first_name = fake["en_CA"].first_name()
    last_name = fake["en_CA"].last_name()

    # 1% chance to add French accent (simulate French-Canadian names)
    first_name = maybe_add_accents(first_name, rng, mc["non_ascii_name"])
    last_name = maybe_add_accents(last_name, rng, mc["non_ascii_name"])

    # Middle initial (60% of members don't have one → None)
    if roll(mc["middle_initial_missing"], rng):
        middle_initial = None
    else:
        middle_initial = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    # --- Employer-dependent fields ---
    # Hire date
    employer_start = employer.participation_start_date
    hire_date = pick_hire_date(dob, employer_start, as_of, rng)
    enrollment_date = pick_enrollment_date(
        plan_start, employer_start, as_of, hire_date, rng,
    )

    # --- Termination date (only for D/R/T/S) ---
    termination_date = None
    if status in ("D", "R", "T", "S"):
        # Terminated sometime between enrollment and as_of
        min_term = enrollment_date + timedelta(days=30)
        if min_term >= as_of:
            termination_date = as_of - timedelta(days=1)
        else:
            termination_date = random_date_between(
                min_term, as_of - timedelta(days=1), rng,
            )

    # --- Marital status ---
    marital = weighted_choice(mcfg["marital_status_distribution"], rng)
    if roll(mc["marital_status_unknown"], rng):
        marital = "U"

    # --- Language ---
    language = weighted_choice(mcfg["language_preference_distribution"], rng)

    # --- Employment type ---
    if status == "A":
        employment_type = weighted_choice(mcfg["employment_type_distribution"], rng)
    else:
        employment_type = "FT"  # Historical default for non-active

    # --- Salary + band ---
    salary_band = pick_salary_band(config, rng)
    salary = compute_salary(status, salary_band, rng)

    # --- Job category ---
    job_category = weighted_choice(mcfg["job_categories"], rng)

    # --- Service years ---
    if status == "A":
        service = pick_service_years_for_active(enrollment_date, as_of)
    elif status in ("D", "R", "T", "S"):
        # Service ended at termination
        if termination_date:
            service_days = (termination_date - enrollment_date).days
        else:
            service_days = 0
        service = max(0.0, min(10.0, service_days / 365.25))
    else:
        service = 0.0

    # --- Accrued pension ---
    accrual_rate = config["contributions"]["accrual_rate"]
    if status == "R":
        accrued_pension = compute_accrued_pension_retired(age, rng)
    elif status in ("A", "D"):
        # Use salary × service × accrual rate
        accrued_pension = compute_accrued_pension(salary, service, accrual_rate)
    else:
        accrued_pension = 0.0

    # --- Buyback eligibility (Active 30%, Deferred 15%) ---
    eligible_buyback_service = None
    last_buyback_leave_end_date = None
    buyback_rate_by_status = {"A": 0.30, "D": 0.15}
    if status in buyback_rate_by_status and roll(buyback_rate_by_status[status], rng):
        # Eligible: 0.1-2.5 years of purchaseable service
        eligible_buyback_service = round(rng.uniform(0.1, 2.5), 2)
        # Leave ended recently (within last 5 years)
        max_leave_end = as_of - timedelta(days=30)
        min_leave_end = as_of - timedelta(days=365 * 5)
        last_buyback_leave_end_date = random_date_between(
            min_leave_end, max_leave_end, rng,
        )

    # --- Normal retirement date = DOB + 65 years ---
    normal_retirement_date = add_years(dob, 65)

    # --- Contact info ---
    city = employer.city
    postal_code = f"{rng.choice('KLMN')}{rng.randint(1,9)}{rng.choice('ABCEHJKLMNPRSTVWXYZ')}{rng.randint(1,9)}{rng.choice('ABCEHJKLMNPRSTVWXYZ')}{rng.randint(1,9)}"

    # Phone (8% missing)
    phone = maybe_null(make_phone(rng), rng, mc["phone_missing"])

    # Email (15% general missing, 35% for 60+)
    email_miss_rate = mc["email_missing_elder"] if age >= 60 else mc["email_missing_general"]
    email = maybe_null(
        make_email(first_name, last_name, employer.operating_name),
        rng,
        email_miss_rate,
    )

    # --- Member_since_date (when joined the plan) ---
    member_since_date = enrollment_date

    # --- Last statement date (annual statement, previous June) ---
    # For active members, last statement was previous June 15
    if status == "A":
        last_statement_date = date(as_of.year - 1, 6, 15)
    else:
        last_statement_date = None

    # --- Beneficiary on file ---
    beneficiary = "Y" if rng.random() < 0.85 else "N"

    # --- Optional trailing whitespace on name ---
    first_name_out = maybe_add_trailing_whitespace(first_name, rng, mc["trailing_whitespace"])
    last_name_out = maybe_add_trailing_whitespace(last_name, rng, mc["trailing_whitespace"])

    # --- Build the record ---
    record = {
        "MEMBER_ID": int(member_id),
        "SIN_LAST_4": int(generate_sin_last_4(member_id)),
        "FIRST_NAME": first_name_out,
        "MIDDLE_INITIAL": middle_initial,
        "LAST_NAME": last_name_out,
        "DOB": dob,
        "SEX_CODE": sex,
        "MARITAL_STATUS_CODE": marital,
        "LANGUAGE_PREFERENCE": language,
        "STREET_ADDRESS": make_street_address(fake["en_CA"]),
        "CITY": city,
        "POSTAL_CODE": postal_code,
        "PHONE": phone,
        "EMAIL": email,
        "EMPLOYER_ID": employer.employer_id,
        "HIRE_DATE": hire_date,
        "ENROLLMENT_DATE": enrollment_date,
        "TERMINATION_DATE": termination_date,
        "STATUS_CODE": status,
        "EMPLOYMENT_TYPE": employment_type,
        "ANNUAL_SALARY": salary,
        "SALARY_BAND_CODE": salary_band["code"],
        "JOB_CATEGORY": job_category,
        "CREDITED_SERVICE_YEARS": service,
        "ELIGIBLE_BUYBACK_SERVICE": eligible_buyback_service,
        "LAST_BUYBACK_LEAVE_END_DATE": last_buyback_leave_end_date,
        "NORMAL_RETIREMENT_DATE": normal_retirement_date,
        "ACCRUED_ANNUAL_PENSION": accrued_pension,
        "BENEFICIARY_ON_FILE": beneficiary,
        "MEMBER_SINCE_DATE": member_since_date,
        "LAST_STATEMENT_DATE": last_statement_date,
    }
    return record


# -----------------------------------------------------------------------------
# Checksum helper
# -----------------------------------------------------------------------------

def compute_checksum(member_ids: list[str]) -> str:
    """First 32 hex chars of SHA256 over concatenated member IDs."""
    h = hashlib.sha256()
    for mid in member_ids:
        h.update(mid.encode("ascii"))
    return h.hexdigest()[:32].upper()


# -----------------------------------------------------------------------------
# Full generation pipeline
# -----------------------------------------------------------------------------

def generate_snapshot(
    snapshot_date: date,
    employers: list[EmployerInfo],
    config: dict,
    messiness: dict,
    layout: FixedWidthLayout,
    output_path: Path,
    rng: random.Random,
    fake,
) -> MemberGenStats:
    """Generate one complete member census file."""
    plan_start = date.fromisoformat(config["plan"]["effective_date"])
    plan_code = config["plan"]["plan_code"]

    stats = MemberGenStats()

    # Build member-to-employer mapping
    mapping = compute_member_to_employer_mapping(employers)
    total_members = len(mapping)
    logger.info("Target member count: %d", total_members)

    # Status counters for trailer
    status_counts = defaultdict(int)
    sum_salary = 0.0
    sum_pension = 0.0
    member_ids_for_checksum = []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Writing to: %s", output_path)

    with FixedWidthWriter(output_path, layout) as w:
        # --- Header ---
        w.write_header({
            "PLAN_CODE": plan_code,
            "AS_OF_DATE": snapshot_date,
            "RECORD_COUNT": total_members,
            "CREATE_TIMESTAMP": __import__("datetime").datetime.now(),
        })

        # --- Detail records ---
        for idx, (seq_in_employer, employer) in enumerate(mapping):
            member_id = generate_member_id(idx + 1)
            record = build_member_record(
                member_id=member_id,
                employer=employer,
                config=config,
                messiness=messiness,
                as_of=snapshot_date,
                plan_start=plan_start,
                rng=rng,
                fake=fake,
            )
            w.write_detail(record)

            # Tally stats
            status = record["STATUS_CODE"]
            status_counts[status] += 1
            stats.per_sex[record["SEX_CODE"]] = stats.per_sex.get(record["SEX_CODE"], 0) + 1
            stats.per_salary_band[record["SALARY_BAND_CODE"]] = (
                stats.per_salary_band.get(record["SALARY_BAND_CODE"], 0) + 1
            )
            if record["ELIGIBLE_BUYBACK_SERVICE"] is not None:
                stats.buyback_eligible_count += 1
            if record["EMAIL"] is None:
                stats.email_missing_count += 1
            sum_salary += record["ANNUAL_SALARY"]
            sum_pension += record["ACCRUED_ANNUAL_PENSION"]
            member_ids_for_checksum.append(member_id)

            if (idx + 1) % 10000 == 0:
                logger.info("  Written %d / %d members", idx + 1, total_members)

        # --- Trailer ---
        checksum = compute_checksum(member_ids_for_checksum)
        w.write_trailer({
            "AS_OF_DATE": snapshot_date,
            "TOTAL_RECORD_COUNT": total_members,
            "ACTIVE_COUNT": status_counts["A"],
            "DEFERRED_COUNT": status_counts["D"],
            "RETIRED_COUNT": status_counts["R"],
            "TERMINATED_COUNT": status_counts["T"],
            "SURVIVOR_COUNT": status_counts["S"],
            "SUM_ANNUAL_SALARY": sum_salary,
            "SUM_ACCRUED_PENSION": sum_pension,
            "CHECKSUM": checksum,
        })

    # Finalize stats
    stats.total_members = total_members
    stats.per_status = dict(status_counts)
    stats.sum_annual_salary = sum_salary
    stats.sum_accrued_pension = sum_pension
    return stats


def generate(
    config_path: Path,
    messiness_path: Path,
    layout_path: Path,
    employer_csv: Path,
    output_dir: Path,
    snapshots_to_generate: list[date],
) -> dict[date, MemberGenStats]:
    """
    Generate one or more member census snapshots.

    For M3 initial version, each snapshot is generated INDEPENDENTLY with the
    same seed (+ date offset). This produces slightly different data per
    snapshot which is enough for "diff detection" pipeline demos.

    A production system would carry state forward (same member_id → same
    person across snapshots). We can enhance this later.
    """
    config = load_yaml(config_path)
    messiness = load_yaml(messiness_path)
    layout = FixedWidthLayout.from_yaml(layout_path)

    logger.info("Loading employers from %s", employer_csv)
    employers = load_employers(employer_csv)
    logger.info("  Loaded %d employers, %d total enrolled members",
                len(employers), sum(e.enrolled_member_count for e in employers))

    plan_code = config["plan"]["plan_code"]
    results = {}

    for snapshot_date in snapshots_to_generate:
        logger.info("=" * 70)
        logger.info("Generating snapshot: %s", snapshot_date.isoformat())
        logger.info("=" * 70)

        # Each snapshot: different seed so data varies
        date_seed_offset = (snapshot_date - date(2024, 1, 1)).days
        seed = config["seeds"]["member"] + date_seed_offset
        rng = random.Random(seed)
        fake = {
            "en_CA": get_multilingual_faker(seed).factories[0],
            "fr_CA": get_multilingual_faker(seed).factories[1],
        }

        filename = f"{plan_code}_MEMBER_CENSUS_{snapshot_date.strftime('%Y%m%d')}.DAT"
        output_path = output_dir / filename

        stats = generate_snapshot(
            snapshot_date=snapshot_date,
            employers=employers,
            config=config,
            messiness=messiness,
            layout=layout,
            output_path=output_path,
            rng=rng,
            fake=fake,
        )
        results[snapshot_date] = stats

    return results


# -----------------------------------------------------------------------------
# Summary printing
# -----------------------------------------------------------------------------

def print_summary(results: dict[date, MemberGenStats]) -> None:
    print()
    print("=" * 70)
    print("Member Generator — Summary")
    print("=" * 70)
    for snapshot_date, stats in results.items():
        print(f"\nSnapshot: {snapshot_date.isoformat()}")
        print(f"  Total members:           {stats.total_members:,}")
        print(f"\n  Status distribution:")
        total = stats.total_members
        for s, code in [("Active", "A"), ("Deferred", "D"), ("Retired", "R"),
                        ("Terminated", "T"), ("Survivor", "S")]:
            cnt = stats.per_status.get(code, 0)
            pct = cnt / total * 100 if total else 0
            print(f"    {s:<12} ({code}): {cnt:>7,} ({pct:5.2f}%)")
        print(f"\n  Sex distribution:")
        for code in ["1", "2", "9"]:
            cnt = stats.per_sex.get(code, 0)
            pct = cnt / total * 100 if total else 0
            label = {"1": "Male", "2": "Female", "9": "Unknown"}[code]
            print(f"    {label:<10} ({code}): {cnt:>7,} ({pct:5.2f}%)")
        print(f"\n  Salary band distribution:")
        for code in ["EN", "MD", "SR", "EX"]:
            cnt = stats.per_salary_band.get(code, 0)
            pct = cnt / total * 100 if total else 0
            print(f"    {code}: {cnt:>7,} ({pct:5.2f}%)")
        print(f"\n  Buyback-eligible:        {stats.buyback_eligible_count:,}")
        print(f"  Email missing:           {stats.email_missing_count:,}  ({stats.email_missing_count/total*100:.1f}%)")
        print(f"  Total annual salary:     ${stats.sum_annual_salary:,.2f}")
        print(f"  Total accrued pension:   ${stats.sum_accrued_pension:,.2f}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ONCAP member census.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--employer-csv", type=Path, default=DEFAULT_EMPLOYER_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--snapshots",
        nargs="+",
        default=["2024-01-31", "2023-12-31"],
        help="ISO dates of snapshots to generate (default: current + prev month)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    snapshots = [date.fromisoformat(s) for s in args.snapshots]

    results = generate(
        config_path=args.config,
        messiness_path=args.messiness,
        layout_path=args.layout,
        employer_csv=args.employer_csv,
        output_dir=args.output_dir,
        snapshots_to_generate=snapshots,
    )
    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
