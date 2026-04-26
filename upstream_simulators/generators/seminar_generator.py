"""
Seminar Attendance Generator — Stage 3e

Generates yearly CSV files of seminar registration and attendance.

Output:
  data/synthetic/seminar_attendance/ONCAP001_SEMINAR_ATTENDANCE_YYYY.csv  × 2 files

Volume: ~15% of members aged 50+ attend each year ≈ ~4,000 attendees/year
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from upstream_simulators.shared.dates import random_date_between
from upstream_simulators.shared.ids import generate_seminar_attendance_id
from upstream_simulators.shared.messiness import roll
from upstream_simulators.shared.writers.delimited import CsvWriter
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census


logger = logging.getLogger("seminar_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "seminar_attendance"

COLUMNS = [
    "attendance_id", "member_id", "seminar_date", "seminar_location",
    "seminar_topic", "attendance_format", "registration_date", "attended_flag",
]

ONTARIO_LOCATIONS = ["Toronto", "Ottawa", "Hamilton", "London", "Mississauga", "Sudbury", "Kingston", "Virtual"]
TOPICS = ["PRE_RETIREMENT", "BUYBACK_101", "INVESTMENT", "GENERAL"]


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
    history_years = config["history"]["seminar_attendance_years"]

    seed = config["seeds"]["seminar"]
    rng = random.Random(seed)
    me = messiness["seminar_attendance"]
    eng = config["engagement"]

    # Active + Deferred members are eligible (the people who care about retirement)
    members = [
        m for m in iter_member_census(member_dat_path, layout)
        if m["STATUS_CODE"] in ("A", "D")
    ]
    logger.info("Eligible members (Active+Deferred): %d", len(members))

    # Members 50+ are most likely to attend
    members_50plus = [
        m for m in members if (as_of - m["DOB"]).days // 365 >= 50
    ]
    members_under_50 = [
        m for m in members if (as_of - m["DOB"]).days // 365 < 50
    ]
    logger.info("Members 50+: %d, under 50: %d", len(members_50plus), len(members_under_50))

    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    total_rows = 0

    # Years to generate
    years = [as_of.year - i - 1 for i in range(history_years)]   # most recent first
    years.sort()

    for year in years:
        # ~15% of 50+ attend, ~5% of under-50 attend
        n_50plus = int(len(members_50plus) * 0.15)
        n_under_50 = int(len(members_under_50) * 0.05)
        annual_attendees = n_50plus + n_under_50

        out_path = output_dir / f"{plan_code}_SEMINAR_ATTENDANCE_{year}.csv"
        with CsvWriter(out_path) as w:
            w.write_header(COLUMNS)
            seq = 0
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)

            attendees = (
                rng.sample(members_50plus, n_50plus) +
                rng.sample(members_under_50, n_under_50)
            )

            for member in attendees:
                seq += 1
                seminar_date = random_date_between(year_start, year_end, rng)
                # Registration 1-60 days before
                reg_date = seminar_date - timedelta(days=rng.randint(1, 60))
                attended = "N" if roll(me["no_show_rate"], rng) else "Y"
                location = rng.choice(ONTARIO_LOCATIONS)
                w.write_row({
                    "attendance_id": generate_seminar_attendance_id(year, seq),
                    "member_id": str(member["MEMBER_ID"]).zfill(10),
                    "seminar_date": seminar_date.isoformat(),
                    "seminar_location": location,
                    "seminar_topic": rng.choice(TOPICS),
                    "attendance_format": "VIRTUAL" if location == "Virtual" else "IN_PERSON",
                    "registration_date": reg_date.isoformat(),
                    "attended_flag": attended,
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
    print(f"\n=== Seminar Attendance Generator ===")
    print(f"  Files written:    {stats['files_written']}")
    print(f"  Total attendees:  {stats['total_rows']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
