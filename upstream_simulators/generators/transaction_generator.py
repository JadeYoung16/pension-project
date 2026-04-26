"""
Transaction Generator — Stage 3a

Generates per-pay-cycle contribution transaction files for 3 months of history.

For each pay date, one file is generated containing transactions from ALL
employers whose pay frequency matches that date's cycle. Multiple pay cycles
can land on the same date (e.g., 2024-01-31 = monthly + semi-monthly EOM).

Output:
  data/synthetic/transactions/ONCAP001_TXN_PAYDATE_YYYYMMDD.TXT  × ~6-8 files/month

File format (pipe-delimited):
  Line 1: H|ONCAP001|TXN|<pay_date>|<record_count>|<create_timestamp>
  Line 2: transaction_id|member_id|employer_id|pay_date|...    (column header)
  Lines 3..N: data rows
  Last line: T|ONCAP001|<record_count>|<sum_member>|<sum_employer>

Business logic:
  - Each active member generates one transaction per pay cycle of their employer
  - pensionable_earnings = annual_salary / pay_periods_per_year
  - member_contribution = earnings × 3%
  - employer_contribution = earnings × 3%
  - 0.5% of transactions get status=RJ (rejected, will be retried)
  - 0.2% have rounding drift in totals
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import csv
import yaml

from upstream_simulators.shared.dates import pay_dates_in_range, pay_period_for_pay_date
from upstream_simulators.shared.ids import generate_transaction_id
from upstream_simulators.shared.messiness import roll
from upstream_simulators.shared.writers.delimited import PipeDelimitedWriter
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census


logger = logging.getLogger("transaction_generator")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_EMPLOYER_CSV = PROJECT_ROOT / "data" / "synthetic" / "employer_registry" / "ONCAP001_EMPLOYER_REGISTRY_20240131.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "transactions"


COLUMNS = [
    "transaction_id", "member_id", "employer_id", "pay_date",
    "pay_period_start", "pay_period_end", "pay_frequency_code",
    "pensionable_earnings", "member_contribution", "employer_contribution",
    "contribution_type", "buyback_reference_id", "transaction_status",
]

PAY_PERIODS_PER_YEAR = {"BW": 26, "SM": 24, "MO": 12, "WK": 52}


@dataclass
class EmployerInfo:
    employer_id: str
    pay_frequency: str


def load_employers(csv_path: Path) -> list[EmployerInfo]:
    employers = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            employers.append(EmployerInfo(
                employer_id=row["employer_id"],
                pay_frequency=row["pay_frequency"],
            ))
    return employers


def load_active_members(member_dat: Path, layout: FixedWidthLayout) -> list[dict]:
    """Return active members with their employer_id and salary."""
    return [
        m for m in iter_member_census(member_dat, layout)
        if m["STATUS_CODE"] == "A" and m["ANNUAL_SALARY"] > 0
    ]


def generate(
    config_path: Path,
    messiness_path: Path,
    layout_path: Path,
    member_dat_path: Path,
    employer_csv: Path,
    output_dir: Path,
) -> dict:
    with config_path.open() as f:
        config = yaml.safe_load(f)
    with messiness_path.open() as f:
        messiness = yaml.safe_load(f)
    layout = FixedWidthLayout.from_yaml(layout_path)

    plan_code = config["plan"]["plan_code"]
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    history_months = config["history"]["transactions_months"]

    # History: last 3 months
    history_end = as_of
    sm = as_of.month - history_months + 1
    sy = as_of.year
    while sm <= 0:
        sm += 12
        sy -= 1
    history_start = date(sy, sm, 1)
    logger.info("History window: %s to %s", history_start, history_end)

    seed = config["seeds"]["transaction"]
    rng = random.Random(seed)
    me = messiness["transactions"]

    # Load employers + members
    employers = load_employers(employer_csv)
    employers_by_id = {e.employer_id: e for e in employers}
    employers_by_freq = defaultdict(list)
    for e in employers:
        employers_by_freq[e.pay_frequency].append(e.employer_id)
    logger.info("Loaded %d employers", len(employers))

    logger.info("Loading active members from member census...")
    active_members = load_active_members(member_dat_path, layout)
    logger.info("  Active members: %d", len(active_members))

    # Group members by employer_id
    members_by_employer = defaultdict(list)
    for m in active_members:
        members_by_employer[m["EMPLOYER_ID"]].append(m)

    # Build pay date schedule for each frequency
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compute paydate → list of (employer_id, frequency) pairs
    paydate_map = defaultdict(list)
    for freq, emp_ids in employers_by_freq.items():
        for pay_date in pay_dates_in_range(history_start, history_end, freq):
            for eid in emp_ids:
                paydate_map[pay_date].append((eid, freq))

    logger.info("Pay dates with transactions: %d", len(paydate_map))

    # Transaction sequence counter (global, monotonic)
    txn_seq = 0
    files_written = 0
    total_rows = 0

    # Tracking duplicate ID injection
    duplicate_pending = None

    for pay_date in sorted(paydate_map.keys()):
        rows = []
        for emp_id, freq in paydate_map[pay_date]:
            members = members_by_employer.get(emp_id, [])
            periods_per_year = PAY_PERIODS_PER_YEAR[freq]
            period_start, period_end = pay_period_for_pay_date(pay_date, freq)

            for m in members:
                txn_seq += 1
                annual_salary = m["ANNUAL_SALARY"]
                earnings = round(annual_salary / periods_per_year, 2)
                # Apply rounding drift messiness occasionally
                if roll(me["rounding_drift"], rng):
                    earnings += rng.choice([-0.01, 0.01])
                member_contrib = round(earnings * 0.03, 2)
                employer_contrib = round(earnings * 0.03, 2)

                status = "RJ" if roll(me["rejected_status"], rng) else "OK"
                pay_period_start = period_start.isoformat()
                # 2% missing pay_period_start
                if roll(me["missing_pay_period_start"], rng):
                    pay_period_start = ""

                txn_id = generate_transaction_id(txn_seq)

                rows.append({
                    "transaction_id": txn_id,
                    "member_id": str(m["MEMBER_ID"]).zfill(10),
                    "employer_id": emp_id,
                    "pay_date": pay_date.isoformat(),
                    "pay_period_start": pay_period_start,
                    "pay_period_end": period_end.isoformat(),
                    "pay_frequency_code": freq,
                    "pensionable_earnings": f"{earnings:.2f}",
                    "member_contribution": f"{member_contrib:.2f}",
                    "employer_contribution": f"{employer_contrib:.2f}",
                    "contribution_type": "REG",
                    "buyback_reference_id": "",
                    "transaction_status": status,
                })

        # Inject one duplicate per month (rare)
        if pay_date.day in (15, 31, 30) and roll(0.3, rng) and rows:
            dup = dict(rows[0])  # Duplicate transaction_id
            dup["pensionable_earnings"] = f"{float(dup['pensionable_earnings']) * 1.05:.2f}"
            rows.append(dup)

        if not rows:
            continue

        sum_member = sum(float(r["member_contribution"]) for r in rows)
        sum_employer = sum(float(r["employer_contribution"]) for r in rows)

        out_path = output_dir / f"{plan_code}_TXN_PAYDATE_{pay_date.strftime('%Y%m%d')}.TXT"
        with PipeDelimitedWriter(out_path) as w:
            ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
            w.write_metadata_line("H", plan_code, "TXN", pay_date.isoformat(), len(rows), ts)
            w.write_column_header(COLUMNS)
            for r in rows:
                w.write_row(r, COLUMNS)
            w.write_metadata_line("T", plan_code, len(rows), f"{sum_member:.2f}", f"{sum_employer:.2f}")

        files_written += 1
        total_rows += len(rows)

    return {
        "files_written": files_written,
        "total_rows": total_rows,
        "pay_dates": len(paydate_map),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    parser.add_argument("--employer-csv", type=Path, default=DEFAULT_EMPLOYER_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = generate(
        args.config, args.messiness, args.layout,
        args.member_dat, args.employer_csv, args.output_dir,
    )
    print(f"\n=== Transaction Generator ===")
    print(f"  Files written:  {stats['files_written']}")
    print(f"  Pay dates:      {stats['pay_dates']}")
    print(f"  Total rows:     {stats['total_rows']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
