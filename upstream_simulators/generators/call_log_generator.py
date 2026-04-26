"""
Call Log Generator — Stage 3d

Generates monthly CSV files of call center contacts.

Output:
  data/synthetic/call_logs/ONCAP001_CALL_LOG_YYYYMM.csv  × 3 files

Volume: ~60 calls per 100 active members per year ≈ 2,500 calls/month.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from upstream_simulators.shared.dates import random_date_between
from upstream_simulators.shared.ids import generate_call_id
from upstream_simulators.shared.messiness import maybe_garbage_notes, maybe_null, roll
from upstream_simulators.shared.writers.delimited import CsvWriter
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census


logger = logging.getLogger("call_log_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "call_logs"

COLUMNS = [
    "call_id", "member_id", "call_timestamp", "duration_seconds",
    "call_reason_category", "call_reason_subcategory", "resolution_code",
    "agent_id", "csat_score", "notes",
]

REASONS = {
    "GENERAL": ["INFO", "REGISTRATION_HELP", "WEBSITE_ISSUE"],
    "BUYBACK": ["COST_INQUIRY", "ELIGIBILITY", "INSTALLMENT_OPTIONS", "DEADLINE_CONFIRM"],
    "RETIREMENT": ["DATE_PROJECTION", "PENSION_AMOUNT", "OPTION_SELECTION"],
    "STATEMENT": ["ANNUAL_REQUEST", "DISCREPANCY", "ADDRESS_UPDATE"],
    "BENEFICIARY": ["UPDATE", "DEATH_BENEFIT"],
    "COMPLAINT": ["DELAYED_PAYMENT", "STAFF_INTERACTION", "OTHER"],
}

NOTES_TEMPLATES = {
    "BUYBACK": "Discussed maternity leave buyback cost and installment options",
    "RETIREMENT": "Provided retirement date projection",
    "STATEMENT": "Resolved annual statement question",
    "BENEFICIARY": "Updated beneficiary on file",
    "COMPLAINT": "Logged complaint, escalated to supervisor",
    "GENERAL": "Answered general inquiry",
}


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

    plan_code = config["plan"]["plan_code"]
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    history_months = config["history"]["call_logs_months"]

    # Build month list
    months = []
    cur_month = as_of.replace(day=1)
    for _ in range(history_months):
        months.append(cur_month)
        # Step back one month
        if cur_month.month == 1:
            cur_month = cur_month.replace(year=cur_month.year - 1, month=12)
        else:
            cur_month = cur_month.replace(month=cur_month.month - 1)
    months = sorted(months)

    seed = config["seeds"]["call"]
    rng = random.Random(seed)
    me = messiness["call_logs"]
    eng = config["engagement"]

    active_members = [
        m for m in iter_member_census(member_dat_path, layout)
        if m["STATUS_CODE"] == "A"
    ]
    logger.info("Active members: %d", len(active_members))

    annual_call_rate = eng["call_center_contact_per_year"]
    monthly_calls_total = int(annual_call_rate * len(active_members) / 12)
    logger.info("Calls per month: %d", monthly_calls_total)

    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    total_rows = 0

    for month_start in months:
        # Compute month end
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)
        month_end = next_month_start - timedelta(days=1)

        out_path = output_dir / f"{plan_code}_CALL_LOG_{month_start.strftime('%Y%m')}.csv"
        with CsvWriter(out_path) as w:
            w.write_header(COLUMNS)
            seq = 0
            for _ in range(monthly_calls_total):
                seq += 1
                call_dt_date = random_date_between(month_start, month_end, rng)
                call_dt = datetime.combine(
                    call_dt_date,
                    datetime.min.time().replace(
                        hour=rng.randint(8, 19), minute=rng.randint(0, 59),
                        second=rng.randint(0, 59),
                    ),
                )
                member = rng.choice(active_members)
                category = rng.choice(list(REASONS.keys()))
                subcategory = rng.choice(REASONS[category])

                duration = int(rng.triangular(60, 1800, 300))
                resolution = rng.choices(
                    ["RESOLVED", "ESCALATED", "CALLBACK", "UNRESOLVED"],
                    weights=[0.75, 0.10, 0.10, 0.05], k=1,
                )[0]
                csat = maybe_null(rng.randint(1, 5), rng, me["csat_score_null"])
                base_notes = NOTES_TEMPLATES.get(category, "")
                notes = maybe_garbage_notes(base_notes, rng, me["notes_garbled"])

                w.write_row({
                    "call_id": generate_call_id(call_dt_date, seq),
                    "member_id": str(member["MEMBER_ID"]).zfill(10),
                    "call_timestamp": call_dt.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                    "duration_seconds": duration,
                    "call_reason_category": category,
                    "call_reason_subcategory": subcategory,
                    "resolution_code": resolution,
                    "agent_id": f"AGT{rng.randint(1, 80):04d}",
                    "csat_score": csat if csat is not None else "",
                    "notes": notes,
                })
                total_rows += 1

        files_written += 1

    return {"files_written": files_written, "total_rows": total_rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    stats = generate(args.config, args.messiness, args.layout,
                     args.member_dat, args.output_dir)
    print(f"\n=== Call Log Generator ===")
    print(f"  Files written: {stats['files_written']}")
    print(f"  Total calls:   {stats['total_rows']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
