"""
Salary History Generator — Stage 3b

Generates the employer-portal salary feed: effective-dated salary history,
one row per member per salary change. This is the UPSTREAM input layer to the
pension calculation engine (pensionable_earnings → contribution already consume
census.ANNUAL_SALARY; this feed is the source-of-record behind that value).

Anchoring (§11 verified against member_census + transaction_generator):
  - member_id / employer_id are sourced from the SAME census records that
    transaction_generator reads, so the three tables join byte-for-byte.
  - The LATEST salary per member ≈ census ANNUAL_SALARY (small anchor drift),
    so portal-latest / census-current / pensionable_earnings stay self-consistent.
  - History depth is driven by census CREDITED_SERVICE_YEARS (capped at
    max_lookback_years), ending at TERMINATION_DATE or as_of. A 0.1-year member
    gets 1 row; an 8-year member gets up to ~5.
  - Members with ANNUAL_SALARY = 0 (R/T/S) get an in-service history sampled
    from their SALARY_BAND_CODE → census-current = 0 while portal has history
    (a real reconciliation/DQ scenario, by design).

Output:
  data/synthetic/salary_history/ONCAP001_SALARY_HISTORY_20240131.csv

Columns:
  member_id, employer_id, effective_date, annual_salary, change_reason, reported_at

Messiness (from messiness_config.yaml: salary_history):
  missing_annual_salary, negative_salary (→ CORRECTION), outlier_10x,
  duplicate_record (resubmission, later reported_at), backdated_report
  (reported_at 1-6 months after effective_date), orphan_member (member_id
  not in census).

Usage:
  python -m upstream_simulators.generators.salary_history_generator
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census
from upstream_simulators.shared.messiness import roll


logger = logging.getLogger("salary_history_generator")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "salary_history"


COLUMNS = [
    "member_id", "employer_id", "effective_date",
    "annual_salary", "change_reason", "reported_at",
]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def build_band_ranges(config: dict) -> dict[str, tuple[float, float]]:
    """salary_band_code → (lo, hi) from plan_config."""
    return {b["code"]: tuple(b["range"]) for b in config["members"]["salary_bands"]}


def make_reported_at(
    effective_date: date, sh_msg: dict, rng: random.Random
) -> tuple[datetime, bool]:
    """
    reported_at ≈ effective_date normally (0-3 days). With backdated_report
    probability, reported 1-6 months LATE (retroactive/backdated change).
    """
    backdated = roll(sh_msg["backdated_report"], rng)
    delay_days = rng.randint(30, 180) if backdated else rng.randint(0, 3)
    dt = datetime(
        effective_date.year, effective_date.month, effective_date.day,
        rng.randint(8, 17), rng.randint(0, 59), rng.randint(0, 59),
    ) + timedelta(days=delay_days)
    return dt, backdated


def build_member_history(
    member: dict,
    band_ranges: dict[str, tuple[float, float]],
    sh_cfg: dict,
    as_of: date,
    rng: random.Random,
) -> tuple[list[dict], float]:
    """
    Build one member's clean salary history (pre-messiness), ascending by
    effective_date. Returns (records, latest_salary).
    """
    census_salary = member["ANNUAL_SALARY"] or 0.0
    band_code = member["SALARY_BAND_CODE"]
    term_date = member["TERMINATION_DATE"]
    service = member["CREDITED_SERVICE_YEARS"] or 0.0

    # Anchor = current salary. Census ANNUAL_SALARY when in pay; else band-sample.
    if census_salary > 0:
        anchor = census_salary
    else:
        lo, hi = band_ranges.get(band_code, (35000.0, 50000.0))
        anchor = round(rng.uniform(lo, hi), 2)

    # Window: depth = service (capped), ending at termination or as_of.
    end = term_date if term_date else as_of
    span_years = min(service, sh_cfg["max_lookback_years"])
    start = end - timedelta(days=int(span_years * 365.25))

    # Review points = review_effective_month/day each year, strictly after start.
    review_dates = []
    for year in range(start.year, end.year + 1):
        d = date(year, sh_cfg["review_effective_month"], sh_cfg["review_effective_day"])
        if start < d <= end:
            review_dates.append(d)
    raise_dates = [d for d in review_dates if roll(sh_cfg["annual_review_raise_prob"], rng)]

    effective_dates = [start] + raise_dates  # ascending; index 0 = INITIAL
    n = len(effective_dates)

    # Latest salary ≈ anchor (± drift). Walk backwards dividing out each raise.
    drift = rng.uniform(-sh_cfg["anchor_drift_pct"], sh_cfg["anchor_drift_pct"])
    latest_salary = round(anchor * (1 + drift), 2)

    salaries = [0.0] * n
    reasons: list[str | None] = [None] * n
    salaries[-1] = latest_salary
    for i in range(n - 1, 0, -1):
        # Raise applied AT effective_dates[i] (transition i-1 → i).
        if roll(sh_cfg["promotion_share"], rng):
            pct = rng.uniform(*sh_cfg["promotion_raise_pct_range"])
            reasons[i] = "PROMOTION"
        else:
            pct = rng.uniform(*sh_cfg["cola_raise_pct_range"])
            reasons[i] = "COLA"
        salaries[i - 1] = round(salaries[i] / (1 + pct), 2)
    reasons[0] = "INITIAL"

    mid = str(member["MEMBER_ID"]).zfill(10)   # ← byte-identical to transaction
    emp_id = member["EMPLOYER_ID"]             # ← already EMP####### in census
    records = [
        {
            "member_id": mid,
            "employer_id": emp_id,
            "effective_date": eff,
            "annual_salary": sal,
            "change_reason": rsn,
        }
        for eff, sal, rsn in zip(effective_dates, salaries, reasons)
    ]
    return records, latest_salary


def emit_record(
    rec: dict, sh_msg: dict, rng: random.Random, stats: dict
) -> list[dict]:
    """Apply value/timing messiness; return 1 row (or 2 if duplicated)."""
    salary = rec["annual_salary"]
    reason = rec["change_reason"]

    if roll(sh_msg["outlier_10x"], rng):
        salary = round(salary * 10, 2)
        stats["outlier"] += 1
    if roll(sh_msg["negative_salary"], rng):
        salary = -abs(salary)
        reason = "CORRECTION"          # reversal recorded as negative
        stats["negative"] += 1
    missing = roll(sh_msg["missing_annual_salary"], rng)
    if missing:
        stats["missing"] += 1

    reported_at, backdated = make_reported_at(rec["effective_date"], sh_msg, rng)
    if backdated:
        stats["backdated"] += 1

    out = {
        "member_id": rec["member_id"],
        "employer_id": rec["employer_id"],
        "effective_date": rec["effective_date"].isoformat(),
        "annual_salary": "" if missing else f"{salary:.2f}",
        "change_reason": reason,
        "reported_at": reported_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    rows = [out]

    if roll(sh_msg["duplicate_record"], rng):
        dup = dict(out)
        # Resubmission: same natural key, later reported_at.
        dup["reported_at"] = (
            reported_at + timedelta(hours=rng.randint(1, 48))
        ).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(dup)
        stats["duplicate"] += 1

    return rows


def make_orphan_rows(
    n_orphans: int,
    employer_ids: list[str],
    band_ranges: dict[str, tuple[float, float]],
    sh_cfg: dict,
    rng: random.Random,
) -> list[dict]:
    """member_id outside census range (50001-59999) → fails FK to dim_member."""
    lo, hi = band_ranges["MD"]
    rows = []
    for _ in range(n_orphans):
        eff = date(2023, sh_cfg["review_effective_month"], sh_cfg["review_effective_day"])
        reported = datetime(eff.year, eff.month, eff.day, rng.randint(8, 17), rng.randint(0, 59))
        rows.append({
            "member_id": str(rng.randint(50001, 59999)).zfill(10),
            "employer_id": rng.choice(employer_ids),
            "effective_date": eff.isoformat(),
            "annual_salary": f"{round(rng.uniform(lo, hi), 2):.2f}",
            "change_reason": "INITIAL",
            "reported_at": reported.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    return rows


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------

def generate(
    config_path: Path,
    messiness_path: Path,
    layout_path: Path,
    member_dat_path: Path,
    output_dir: Path,
) -> dict:
    with config_path.open() as f:
        config = yaml.safe_load(f)
    with messiness_path.open() as f:
        messiness = yaml.safe_load(f)
    layout = FixedWidthLayout.from_yaml(layout_path)

    sh_cfg = config["salary_history"]
    sh_msg = messiness["salary_history"]
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    plan_code = config["plan"]["plan_code"]
    rng = random.Random(config["seeds"]["salary"])
    band_ranges = build_band_ranges(config)

    stats: dict[str, int] = defaultdict(int)
    reason_counter: Counter = Counter()
    per_member_counter: Counter = Counter()
    employer_ids: set[str] = set()
    drift_samples: list[float] = []   # |latest/census - 1| for in-pay members
    all_rows: list[dict] = []
    member_count = 0

    logger.info("Reading census: %s", member_dat_path)
    for m in iter_member_census(member_dat_path, layout):
        member_count += 1
        employer_ids.add(m["EMPLOYER_ID"])
        recs, latest = build_member_history(m, band_ranges, sh_cfg, as_of, rng)
        per_member_counter[len(recs)] += 1
        if (m["ANNUAL_SALARY"] or 0) > 0:
            drift_samples.append(abs(latest / m["ANNUAL_SALARY"] - 1))
        for rec in recs:
            reason_counter[rec["change_reason"]] += 1
            all_rows.extend(emit_record(rec, sh_msg, rng, stats))
        if member_count % 10000 == 0:
            logger.info("  Processed %d members", member_count)

    n_orphans = int(sh_msg["orphan_member"] * member_count)
    orphan_rows = make_orphan_rows(n_orphans, sorted(employer_ids), band_ranges, sh_cfg, rng)
    all_rows.extend(orphan_rows)
    stats["orphan"] = len(orphan_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{plan_code}_SALARY_HISTORY_{as_of.strftime('%Y%m%d')}.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    logger.info("Wrote %s (%d rows)", out_path, len(all_rows))

    return {
        "out_path": out_path,
        "total_rows": len(all_rows),
        "member_count": member_count,
        "stats": dict(stats),
        "reason_counter": reason_counter,
        "per_member_counter": per_member_counter,
        "max_drift": max(drift_samples) if drift_samples else 0.0,
        "anchor_drift_pct": sh_cfg["anchor_drift_pct"],
    }


def print_summary(r: dict) -> None:
    total = r["total_rows"]
    print("\n" + "=" * 70)
    print("Salary History Generator — Summary")
    print("=" * 70)
    print(f"  Output:              {r['out_path']}")
    print(f"  Members covered:     {r['member_count']:,}")
    print(f"  Total rows:          {total:,}")

    print("\n  Records per member:")
    for k in sorted(r["per_member_counter"]):
        c = r["per_member_counter"][k]
        print(f"    {k} record(s): {c:>7,} members ({c / r['member_count'] * 100:5.1f}%)")

    print("\n  change_reason distribution:")
    for reason, c in r["reason_counter"].most_common():
        print(f"    {reason:<11}: {c:>8,} ({c / total * 100:5.2f}%)")

    print("\n  Dirty data — row-level (rate of total rows):")
    row_targets = {
        "missing": 0.02, "negative": 0.003, "outlier": 0.001,
        "duplicate": 0.005, "backdated": 0.04,
    }
    for k, tgt in row_targets.items():
        c = r["stats"].get(k, 0)
        print(f"    {k:<10}: {c:>7,} ({c / total * 100:5.3f}%  target {tgt * 100:.2f}%)")

    print("\n  Dirty data — member-level (rate of members):")
    orphan_c = r["stats"].get("orphan", 0)
    print(f"    {'orphan':<10}: {orphan_c:>7,} ({orphan_c / r['member_count'] * 100:5.3f}%  "
          f"target 0.20%)")

    print(f"\n  Anchor drift (in-pay members): max |latest/census - 1| = "
          f"{r['max_drift'] * 100:.3f}%  (bound {r['anchor_drift_pct'] * 100:.2f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ONCAP salary history portal feed.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    r = generate(args.config, args.messiness, args.layout, args.member_dat, args.output_dir)
    print_summary(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())