"""
Employer Generator — Stage 1

Generates the ONCAP employer registry by sampling real Ontario non-profit
organizations from the CRA T3010 charity data, stratified by employee count
into 4 size bands (LARGE / MEDIUM / SMALL / MICRO).

Output: data/synthetic/employer_registry/ONCAP001_EMPLOYER_REGISTRY_YYYYMMDD.csv

Why this design:
  - Real organization names from T3010 give the dataset authentic feel
  - Size bands reflect realistic non-profit employer distribution
  - Member count allocation per employer → sums exactly to target (50,000)
  - Pay frequency assignment is independent of size band (random)
  - Acquisition attributes (channel/source/first_contact_date) support the
    upper-funnel employer-acquisition mart in Week 6 (see project plan §7.6).

Dependencies:
  - data/raw_external/cra_t3010_2023/ident_2023_ontario.csv
  - data/raw_external/cra_t3010_2023/financial_section_a_b_and_c_2023.csv
  - upstream_simulators/config/plan_config.yaml
  - upstream_simulators/config/messiness_config.yaml

Usage:
  python -m upstream_simulators.generators.employer_generator
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from upstream_simulators.shared.faker_pool import get_faker
from upstream_simulators.shared.ids import generate_employer_id
from upstream_simulators.shared.writers.delimited import CsvWriter


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("employer_generator")


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_T3010_IDENT = (
    PROJECT_ROOT / "data" / "raw_external" / "cra_t3010_2023" / "ident_2023_ontario.csv"
)
# NOTE: Despite the variable name, we load Schedule 3 (compensation) because
# that's where employee counts live (lines 300 = FT, 370 = PT).
# The "financial" D/Schedule 6 file contains ASSET amounts (line 4100 = cash),
# not employee counts — a common T3010 confusion.
DEFAULT_T3010_SCHEDULE3 = (
    PROJECT_ROOT / "data" / "raw_external" / "cra_t3010_2023"
    / "schedule_3_compensation_2023.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "employer_registry"


# -----------------------------------------------------------------------------
# Column definitions
# -----------------------------------------------------------------------------

OUTPUT_COLUMNS = [
    "employer_id",
    "business_number",
    "legal_name",
    "operating_name",
    "sector_category_code",
    "city",
    "postal_code",
    "employer_size_band",
    "employee_count",
    "enrolled_member_count",
    "pay_frequency",
    "participation_start_date",
    "plan_administrator_name",
    "plan_administrator_email",
    "status",
    # Acquisition funnel attributes (Week 4)
    "acquisition_channel",
    "prospect_source",
    "first_contact_date",
]


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------


@dataclass
class EmployerSizeBand:
    """Size band definition from plan_config.yaml."""

    name: str
    target_count: int
    employee_count_range: tuple[int, int]
    members_per_employer_avg: int


@dataclass
class T3010Row:
    """One row joined from CRA T3010 ident + financial data."""

    bn: str
    legal_name: str
    operating_name: str
    category: str
    city: str
    postal_code: str
    employee_count: int

    @property
    def size_band_name(self) -> Optional[str]:
        """Return band name based on employee count, or None if unassigned."""
        ec = self.employee_count
        if ec >= 200:
            return "LARGE"
        if ec >= 50:
            return "MEDIUM"
        if ec >= 10:
            return "SMALL"
        if ec >= 1:
            return "MICRO"
        return None


@dataclass
class GenerationStats:
    """Summary statistics for the run."""

    total_source_rows: int = 0
    rows_after_filter: int = 0
    per_band_available: dict[str, int] = field(default_factory=dict)
    per_band_selected: dict[str, int] = field(default_factory=dict)
    per_band_member_count: dict[str, int] = field(default_factory=dict)
    pay_frequency_counts: dict[str, int] = field(default_factory=dict)
    total_enrolled_members: int = 0
    # Acquisition stats (Week 4)
    acquisition_channel_counts: dict[str, int] = field(default_factory=dict)
    prospect_source_counts: dict[str, int] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Config loading
# -----------------------------------------------------------------------------


def load_config(config_path: Path) -> dict:
    """Load plan_config.yaml."""
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_size_bands(config: dict) -> list[EmployerSizeBand]:
    """Extract size band definitions from config."""
    bands = []
    for band_def in config["employers"]["size_bands"]:
        bands.append(
            EmployerSizeBand(
                name=band_def["name"],
                target_count=band_def["count"],
                employee_count_range=tuple(band_def["employee_count_range"]),
                members_per_employer_avg=band_def["members_per_employer_avg"],
            )
        )
    return bands


# -----------------------------------------------------------------------------
# T3010 loading + joining
# -----------------------------------------------------------------------------

def _read_csv_with_encoding_fallback(path: Path, **kwargs) -> pd.DataFrame:
    """
    Read a CSV trying common encodings in order, preferring utf-8-sig to
    strip BOM correctly.

    CRA T3010 files are inconsistently encoded across years/versions:
      - ident_2023_update.csv → UTF-8 with BOM
      - financial_section_a_b_and_c_2023.csv → cp1252 (has non-ASCII bytes)
      - financial_d_and_schedule_6_2023_updated.csv → UTF-8 with BOM

    We try utf-8-sig first (which handles BOM). If it hits a byte it can't
    decode, fall back to cp1252 / iso-8859-1.

    After a successful read, if the first column name starts with 'ï»¿'
    (indicating UTF-8 BOM decoded as cp1252), we strip it so downstream code
    can find 'BN' correctly.
    """
    encodings_to_try = ["utf-8-sig", "cp1252", "iso-8859-1"]
    last_error: Exception | None = None

    for encoding in encodings_to_try:
        try:
            df = pd.read_csv(path, encoding=encoding, **kwargs)
            if encoding != "utf-8-sig":
                logger.warning(
                    "  Fell back to encoding=%s for %s (UTF-8 failed)",
                    encoding, path.name,
                )
            # Defensive fix: if UTF-8 BOM leaked through as 'ï»¿' prefix
            # (happens if cp1252 was tried on a utf-8-sig file), strip it.
            if df.columns[0].startswith("\ufeff"):
                df = df.rename(columns={df.columns[0]: df.columns[0].lstrip("\ufeff")})
            if df.columns[0].startswith("ï»¿"):
                df = df.rename(columns={df.columns[0]: df.columns[0][3:]})
            return df
        except UnicodeDecodeError as e:
            last_error = e
            continue
    raise UnicodeDecodeError(
        "utf-8",
        b"",
        0, 0,
        f"Could not decode {path} with any of {encodings_to_try}. Last error: {last_error}",
    )


def load_t3010_data(
    ident_path: Path,
    schedule3_path: Path,
) -> list[T3010Row]:
    """
    Load CRA T3010 ident + Schedule 3 Compensation files, join on BN,
    return filtered rows.

    Column mapping (Schedule 3):
      - 300 = Number of permanent, full-time, compensated positions
      - 370 = Number of part-time or part-year employees
      - Other columns (305-345) are compensation range buckets (not used here)

    Filters applied:
      - Ontario only (already pre-filtered in ident_2023_ontario.csv)
      - (FT + PT) ≥ 1
      - Legal name not empty
      - Religious/faith category (30, 40, 60, 70) with FT > 500 dropped as
        likely data-entry errors (small religious orgs reporting tens of
        thousands of FT positions are implausible — CRA does not validate
        these fields)
    """
    if not ident_path.exists():
        raise FileNotFoundError(
            f"CRA T3010 ident file not found: {ident_path}\n"
            "Run downloaders/download_cra_t3010.py first."
        )
    if not schedule3_path.exists():
        raise FileNotFoundError(
            f"CRA T3010 Schedule 3 file not found: {schedule3_path}\n"
            "Run downloaders/download_cra_t3010.py first."
        )

    logger.info("Loading T3010 ident file: %s", ident_path.name)
    ident_df = _read_csv_with_encoding_fallback(ident_path, dtype=str)
    logger.info("  Ident rows: %d", len(ident_df))

    logger.info("Loading T3010 Schedule 3 file: %s", schedule3_path.name)
    sched3_df = _read_csv_with_encoding_fallback(
        schedule3_path,
        dtype=str,
        usecols=lambda c: c in ("BN", "300", "370"),
    )
    logger.info("  Schedule 3 rows (all provinces): %d", len(sched3_df))

    # Inner join
    merged = ident_df.merge(sched3_df, on="BN", how="inner")
    logger.info("  Inner-joined (Ontario) rows: %d", len(merged))

    # Categories likely to have data quality issues at large values
    SUSPECT_CATEGORIES = {"30", "40", "60", "70"}   # religious/faith groups
    SUSPECT_CAT_FT_CEILING = 500

    rows = []
    dropped_suspect = 0
    dropped_no_data = 0
    dropped_no_name = 0

    for _, row in merged.iterrows():
        legal_name = str(row.get("Legal Name") or "").strip()
        if not legal_name:
            dropped_no_name += 1
            continue

        def _to_int(v):
            try:
                return int(float(v)) if v is not None and str(v).strip() != "" else 0
            except (ValueError, TypeError):
                return 0

        ft = _to_int(row.get("300"))
        pt = _to_int(row.get("370"))
        total_employees = ft + pt

        if total_employees < 1:
            dropped_no_data += 1
            continue

        # Drop religious charities with suspicious FT (likely data entry errors)
        category = str(row.get("Category") or "").strip()
        if category in SUSPECT_CATEGORIES and ft > SUSPECT_CAT_FT_CEILING:
            dropped_suspect += 1
            continue

        rows.append(
            T3010Row(
                bn=str(row["BN"]).strip(),
                legal_name=legal_name,
                operating_name=str(row.get("Account Name") or "").strip() or legal_name,
                category=category or "000",
                city=str(row.get("City") or "").strip() or "Toronto",
                postal_code=str(row.get("Postal Code") or "").strip() or "M5V3A8",
                employee_count=total_employees,
            )
        )

    logger.info("  Filter summary:")
    logger.info("    Dropped (no legal name):     %d", dropped_no_name)
    logger.info("    Dropped (no employee data):  %d", dropped_no_data)
    logger.info("    Dropped (suspect religious): %d", dropped_suspect)
    logger.info("    Kept:                        %d", len(rows))
    return rows


# -----------------------------------------------------------------------------
# Sampling logic
# -----------------------------------------------------------------------------


def bucket_rows_by_band(rows: list[T3010Row]) -> dict[str, list[T3010Row]]:
    """Group rows into their natural size band."""
    buckets: dict[str, list[T3010Row]] = defaultdict(list)
    for row in rows:
        band = row.size_band_name
        if band:
            buckets[band].append(row)
    return buckets


def sample_employers(
    buckets: dict[str, list[T3010Row]],
    bands: list[EmployerSizeBand],
    rng: random.Random,
) -> list[tuple[T3010Row, str]]:
    """
    Sample employers according to target counts per band.

    Sampling strategy:
      Within each band, use weighted sampling where weight ∝ employee_count.
      This biases selection toward larger employers, which is realistic for
      a pension plan's employer acquisition: larger employers deliver more
      members per onboarding effort, so early plan sponsors tend to be
      disproportionately mid-to-large within each size band.

    Fallback policy: if a band's pool is smaller than the target count,
    borrow top-N largest from the neighboring smaller band.

    Returns list of (T3010Row, assigned_band_name). assigned_band_name may
    differ from T3010Row.size_band_name if a fallback was used.
    """
    selected: list[tuple[T3010Row, str]] = []
    band_order = ["LARGE", "MEDIUM", "SMALL", "MICRO"]
    bands_by_name = {b.name: b for b in bands}

    # Working copy of buckets so we can pop as we consume
    remaining = {name: list(buckets.get(name, [])) for name in band_order}

    def _weighted_sample_without_replacement(
        pool: list[T3010Row], k: int
    ) -> list[T3010Row]:
        """
        Efraimidis-Spirakis weighted reservoir sampling without replacement.
        Each item gets a key = random() ** (1 / weight), we pick top-k by key.
        """
        if k >= len(pool):
            return list(pool)
        keyed = [
            (rng.random() ** (1.0 / max(row.employee_count, 1)), row)
            for row in pool
        ]
        keyed.sort(key=lambda kv: kv[0], reverse=True)
        return [row for _, row in keyed[:k]]

    for band_name in band_order:
        target = bands_by_name[band_name].target_count
        pool = remaining[band_name]

        picks = _weighted_sample_without_replacement(pool, target)
        for row in picks:
            selected.append((row, band_name))
            remaining[band_name] = [r for r in remaining[band_name] if r.bn != row.bn]

        shortfall = target - len(picks)
        if shortfall > 0:
            logger.warning(
                "Band %s shortfall: wanted %d, found %d. Borrowing from next smaller band.",
                band_name, target, len(picks),
            )
            next_smaller_idx = band_order.index(band_name) + 1
            if next_smaller_idx < len(band_order):
                donor_name = band_order[next_smaller_idx]
                donor_pool = remaining[donor_name]
                # Borrow the largest rows from the donor
                donor_pool_sorted = sorted(
                    donor_pool, key=lambda r: r.employee_count, reverse=True
                )
                borrowed = donor_pool_sorted[:shortfall]
                for row in borrowed:
                    selected.append((row, band_name))
                remaining[donor_name] = [
                    r for r in donor_pool if r.bn not in {b.bn for b in borrowed}
                ]
                logger.warning(
                    "  Borrowed %d from %s to fill %s",
                    len(borrowed), donor_name, band_name,
                )
            else:
                logger.error(
                    "  Cannot fulfill shortfall for %s — no smaller band available",
                    band_name,
                )

    return selected


def assign_member_counts(
    selected: list[tuple[T3010Row, str]],
    bands: list[EmployerSizeBand],
    target_total: int,
    rng: random.Random,
) -> list[int]:
    """
    Assign a `enrolled_member_count` to each selected employer.

    Strategy:
      1. Each employer gets a count with ±30% jitter around band average
      2. Cap at 85% of employee_count (realistic enrollment ceiling — not
         every employee is a plan member; part-timers, contractors, new hires
         in waiting period don't participate)
      3. After jitter + cap, scale counts so sum == target_total exactly
      4. Scaling must also respect the cap

    Returns a list of member counts parallel to `selected`.
    """
    bands_by_name = {b.name: b for b in bands}

    # Step 1: jittered counts + hard cap at 85% of employee_count
    raw_counts: list[int] = []
    caps: list[int] = []
    for row, band_name in selected:
        avg = bands_by_name[band_name].members_per_employer_avg
        jitter = rng.uniform(0.7, 1.3)
        raw = max(1, int(avg * jitter))
        # Cap: realistic enrollment is 60-95% of employees, use 85% ceiling
        cap = max(1, int(row.employee_count * 0.85))
        raw_counts.append(min(raw, cap))
        caps.append(cap)

    current_total = sum(raw_counts)
    logger.info(
        "  Pre-adjustment total: %d (target: %d, diff: %+d)",
        current_total, target_total, current_total - target_total,
    )

    # Step 2: scale proportionally (constrained by caps)
    scale = target_total / current_total if current_total > 0 else 1.0
    scaled = [
        min(caps[i], max(1, int(round(c * scale))))
        for i, c in enumerate(raw_counts)
    ]

    # Step 3: fix residual drift from rounding + caps
    # (If we're under target, distribute +1s to employers not yet at cap;
    #  if over target, distribute -1s to employers above 1.)
    for _ in range(100):  # Safety bound
        residual = target_total - sum(scaled)
        if residual == 0:
            break
        step = 1 if residual > 0 else -1
        # Eligible indices: for +step, must be below cap; for -step, must be > 1
        if step > 0:
            eligible = [i for i in range(len(scaled)) if scaled[i] < caps[i]]
        else:
            eligible = [i for i in range(len(scaled)) if scaled[i] > 1]
        if not eligible:
            # Can't adjust further
            logger.warning(
                "Cannot adjust counts to reach exact target. Residual: %d",
                residual,
            )
            break
        # Pick indices weighted toward larger employers when adding, smaller when subtracting
        if step > 0:
            weights = [max(1, caps[i] - scaled[i]) for i in eligible]
        else:
            weights = [scaled[i] for i in eligible]
        pick_count = min(abs(residual), len(eligible))
        picks = rng.choices(eligible, weights=weights, k=pick_count)
        for idx in picks:
            if step > 0 and scaled[idx] < caps[idx]:
                scaled[idx] += 1
            elif step < 0 and scaled[idx] > 1:
                scaled[idx] -= 1

    final_total = sum(scaled)
    logger.info("  Post-adjustment total: %d (target: %d)", final_total, target_total)
    if final_total != target_total:
        logger.warning(
            "Member count allocation hit cap ceiling. Actual total: %d, target: %d. "
            "This means the employer pool doesn't have enough capacity.",
            final_total, target_total,
        )

    return scaled


# -----------------------------------------------------------------------------
# Other attribute generation
# -----------------------------------------------------------------------------


def weighted_choice(choices: dict[str, float], rng: random.Random) -> str:
    """Pick a key from a dict of {value: weight}."""
    items = list(choices.items())
    keys = [k for k, _ in items]
    weights = [w for _, w in items]
    return rng.choices(keys, weights=weights, k=1)[0]


def pick_pay_frequency(config: dict, rng: random.Random) -> str:
    """Pick BW / SM / MO / WK according to configured distribution."""
    return weighted_choice(config["employers"]["pay_frequency_distribution"], rng)


def pick_participation_start_date(
    plan_start: date, as_of: date, rng: random.Random
) -> date:
    """
    Pick a participation start date with 3-tier temporal distribution:
      - 30% early (2014-01-01 to 2017-12-31)
      - 40% mid (2018-01-01 to 2020-12-31)
      - 30% late (2021-01-01 to as_of)

    All dates are adjusted to not exceed as_of.
    """
    buckets = [
        (0.30, plan_start, date(2017, 12, 31)),
        (0.40, date(2018, 1, 1), date(2020, 12, 31)),
        (0.30, date(2021, 1, 1), as_of - timedelta(days=1)),
    ]
    weights = [b[0] for b in buckets]
    bucket_idx = rng.choices(range(len(buckets)), weights=weights, k=1)[0]
    _, start, end = buckets[bucket_idx]
    if end < start:
        end = start
    days_range = (end - start).days
    if days_range <= 0:
        return start
    return start + timedelta(days=rng.randint(0, days_range))


def pick_status(config: dict, rng: random.Random) -> str:
    """Pick ACTIVE or WITHDRAWN."""
    return weighted_choice(config["employers"]["status_distribution"], rng)


def pick_acquisition_channel(config: dict, rng: random.Random) -> str:
    """Pick how the employer was acquired (touch type)."""
    return weighted_choice(
        config["employers"]["acquisition_channel_distribution"], rng
    )


def pick_prospect_source(config: dict, rng: random.Random) -> str:
    """Pick where the lead originated (lead source)."""
    return weighted_choice(
        config["employers"]["prospect_source_distribution"], rng
    )


def pick_first_contact_date(
    participation_start: date,
    channel: str,
    config: dict,
    rng: random.Random,
) -> date:
    """
    Pick first_contact_date = participation_start - sales_cycle_days,
    where sales_cycle_days is drawn from a channel-specific range.

    Channel drives sales cycle length: inbound is short (already interested),
    outbound is long (cold start). This gives Week 6 mart layer a real signal
    to slice funnel velocity by channel.

    Guards against pre-plan-start dates only if the participation date is
    very early; we don't clamp here because some early prospects legitimately
    had multi-year cycles. The mart layer can flag any anomalies.
    """
    cycle_range = config["employers"]["sales_cycle_days_by_channel"].get(
        channel, [60, 365]
    )
    lo, hi = int(cycle_range[0]), int(cycle_range[1])
    days = rng.randint(lo, hi)
    return participation_start - timedelta(days=days)


def make_administrator_email(name: str, operating_name: str) -> str:
    """Synthesize a plan_administrator_email."""
    # Normalize name to first.last format
    parts = [p.strip().lower() for p in name.split() if p.strip()]
    if len(parts) >= 2:
        prefix = f"{parts[0]}.{parts[-1]}"
    elif parts:
        prefix = parts[0]
    else:
        prefix = "admin"
    # Domain from operating name
    domain_base = "".join(c.lower() for c in operating_name if c.isalnum())[:20] or "org"
    return f"{prefix}@{domain_base}.ca"


# -----------------------------------------------------------------------------
# Main generation pipeline
# -----------------------------------------------------------------------------


def generate(
    config: dict,
    ident_path: Path,
    schedule3_path: Path,
    output_dir: Path,
    override_total: Optional[int] = None,
) -> GenerationStats:
    """
    Full employer generation pipeline. Returns run statistics.

    Args:
        config: Parsed plan_config.yaml
        ident_path, financial_path: T3010 data locations
        output_dir: Where to write the output CSV
        override_total: If provided, scale all band target counts to hit this
                        total (useful for testing with smaller data)
    """
    # -------------------- Setup --------------------
    seed = config["seeds"]["employer"]
    rng = random.Random(seed)
    fake = get_faker(seed)

    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    plan_start = date.fromisoformat(config["plan"]["effective_date"])
    plan_code = config["plan"]["plan_code"]

    bands = parse_size_bands(config)

    # Apply override if provided (scale proportionally)
    if override_total is not None:
        original_total = sum(b.target_count for b in bands)
        scale = override_total / original_total
        for b in bands:
            b.target_count = max(1, int(round(b.target_count * scale)))
        logger.info(
            "OVERRIDE: scaling band counts to hit %d total (was %d).",
            override_total, original_total,
        )
        for b in bands:
            logger.info("  %s → %d", b.name, b.target_count)

    stats = GenerationStats()

    # -------------------- Load T3010 --------------------
    t3010_rows = load_t3010_data(ident_path, schedule3_path)
    stats.total_source_rows = len(t3010_rows)
    stats.rows_after_filter = len(t3010_rows)

    # -------------------- Bucket by band --------------------
    buckets = bucket_rows_by_band(t3010_rows)
    for name in ["LARGE", "MEDIUM", "SMALL", "MICRO"]:
        stats.per_band_available[name] = len(buckets.get(name, []))
        logger.info("  %s pool size: %d", name, stats.per_band_available[name])

    # -------------------- Sample --------------------
    selected = sample_employers(buckets, bands, rng)
    logger.info("Selected %d employers total", len(selected))
    for _, band_name in selected:
        stats.per_band_selected[band_name] = stats.per_band_selected.get(band_name, 0) + 1

    # -------------------- Allocate member counts --------------------
    target_members = config["members"]["total_count"]
    if override_total is not None:
        target_members = int(round(target_members * (override_total / sum(b.target_count for b in parse_size_bands(config)))))
        target_members = max(len(selected), target_members)
    member_counts = assign_member_counts(selected, bands, target_members, rng)

    for (_, band_name), count in zip(selected, member_counts):
        stats.per_band_member_count[band_name] = (
            stats.per_band_member_count.get(band_name, 0) + count
        )
    stats.total_enrolled_members = sum(member_counts)

    # -------------------- Write output --------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{plan_code}_EMPLOYER_REGISTRY_{as_of.strftime('%Y%m%d')}.csv"
    output_path = output_dir / filename

    logger.info("Writing %d rows to %s", len(selected), output_path)

    with CsvWriter(output_path) as w:
        w.write_header(OUTPUT_COLUMNS)

        for seq, ((row, band_name), member_count) in enumerate(
            zip(selected, member_counts), start=1
        ):
            pay_freq = pick_pay_frequency(config, rng)
            stats.pay_frequency_counts[pay_freq] = (
                stats.pay_frequency_counts.get(pay_freq, 0) + 1
            )
            start_date = pick_participation_start_date(plan_start, as_of, rng)
            admin_name = fake.name()
            admin_email = make_administrator_email(admin_name, row.operating_name)

            # Acquisition attributes (Week 4)
            channel = pick_acquisition_channel(config, rng)
            source = pick_prospect_source(config, rng)
            first_contact = pick_first_contact_date(start_date, channel, config, rng)
            stats.acquisition_channel_counts[channel] = (
                stats.acquisition_channel_counts.get(channel, 0) + 1
            )
            stats.prospect_source_counts[source] = (
                stats.prospect_source_counts.get(source, 0) + 1
            )

            w.write_row({
                "employer_id": generate_employer_id(seq),
                "business_number": row.bn,
                "legal_name": row.legal_name,
                "operating_name": row.operating_name,
                "sector_category_code": row.category,
                "city": row.city,
                "postal_code": row.postal_code,
                "employer_size_band": band_name,
                "employee_count": row.employee_count,
                "enrolled_member_count": member_count,
                "pay_frequency": pay_freq,
                "participation_start_date": start_date.isoformat(),
                "plan_administrator_name": admin_name,
                "plan_administrator_email": admin_email,
                "status": pick_status(config, rng),
                "acquisition_channel": channel,
                "prospect_source": source,
                "first_contact_date": first_contact.isoformat(),
            })

    logger.info("Output written: %s", output_path)
    return stats


# -----------------------------------------------------------------------------
# Summary printing
# -----------------------------------------------------------------------------


def print_summary(stats: GenerationStats) -> None:
    print()
    print("=" * 70)
    print("Employer Generator — Summary")
    print("=" * 70)
    print(f"T3010 source rows (after filter):   {stats.rows_after_filter:,}")
    print()
    print(f"{'Band':<8} {'Available':>10} {'Selected':>10} {'Members':>10}")
    print(f"{'-' * 8:<8} {'-' * 10:>10} {'-' * 10:>10} {'-' * 10:>10}")
    for band in ["LARGE", "MEDIUM", "SMALL", "MICRO"]:
        print(
            f"{band:<8} "
            f"{stats.per_band_available.get(band, 0):>10,} "
            f"{stats.per_band_selected.get(band, 0):>10,} "
            f"{stats.per_band_member_count.get(band, 0):>10,}"
        )
    print(f"{'Total':<8} "
          f"{sum(stats.per_band_available.values()):>10,} "
          f"{sum(stats.per_band_selected.values()):>10,} "
          f"{stats.total_enrolled_members:>10,}")
    print()
    print("Pay frequency distribution:")
    total = sum(stats.pay_frequency_counts.values())
    for freq in ["BW", "SM", "MO", "WK"]:
        count = stats.pay_frequency_counts.get(freq, 0)
        pct = count / total * 100 if total else 0
        print(f"  {freq}: {count:>5,} ({pct:5.1f}%)")

    print()
    print("Acquisition channel distribution:")
    total_ch = sum(stats.acquisition_channel_counts.values())
    for ch in sorted(stats.acquisition_channel_counts.keys()):
        count = stats.acquisition_channel_counts[ch]
        pct = count / total_ch * 100 if total_ch else 0
        print(f"  {ch:<12}: {count:>5,} ({pct:5.1f}%)")

    print()
    print("Prospect source distribution:")
    total_src = sum(stats.prospect_source_counts.values())
    for src in sorted(stats.prospect_source_counts.keys()):
        count = stats.prospect_source_counts[src]
        pct = count / total_src * 100 if total_src else 0
        print(f"  {src:<28}: {count:>5,} ({pct:5.1f}%)")


# -----------------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate ONCAP employer registry from CRA T3010 Ontario data."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--t3010-ident", type=Path, default=DEFAULT_T3010_IDENT)
    parser.add_argument("--t3010-schedule3", type=Path, default=DEFAULT_T3010_SCHEDULE3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--override-total",
        type=int,
        default=None,
        help="Reduce total employer count for testing (proportional across bands)",
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

    config = load_config(args.config)
    stats = generate(
        config=config,
        ident_path=args.t3010_ident,
        schedule3_path=args.t3010_schedule3,
        output_dir=args.output_dir,
        override_total=args.override_total,
    )
    print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())