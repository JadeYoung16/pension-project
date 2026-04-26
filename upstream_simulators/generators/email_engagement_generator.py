"""
Email Engagement Generator — Stage 3f

Generates monthly CSV files of email campaign engagement events (sent, opened,
clicked, bounced, unsubscribed).

Output:
  data/synthetic/email_engagement/ONCAP001_EMAIL_ENGAGEMENT_YYYYMM.csv  × 3 files

Volume:
  - ~4 emails sent per active member per year × 27,280 ≈ 9k SENT/month
  - Each SENT spawns DELIVERED (90%), OPENED (35%), CLICKED (10%)
  - Plus BOUNCE (8%) and UNSUBSCRIBE (0.5%)
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
from upstream_simulators.shared.ids import generate_email_event_id
from upstream_simulators.shared.messiness import roll
from upstream_simulators.shared.writers.delimited import CsvWriter
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census


logger = logging.getLogger("email_engagement_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "email_engagement"

COLUMNS = [
    "event_id", "member_id", "campaign_id", "campaign_name",
    "event_type", "event_timestamp", "link_url_clicked",
]

CAMPAIGNS = {
    "Q1_BBK_REM": ("CAMP_Q1_2024_BBK_REM", "Q1 2024 Buyback Reminder",
                   "https://oncap.example.org/buyback-info"),
    "Q1_STMT": ("CAMP_Q1_2024_STMT", "Annual Statement Available",
                "https://oncap.example.org/statements"),
    "Q1_RETIRE_TIPS": ("CAMP_Q1_2024_RETIRE", "Plan Your Retirement",
                       "https://oncap.example.org/retirement-tips"),
    "GENERAL_NEWSLETTER": ("CAMP_NEWSLETTER", "ONCAP Member Newsletter",
                           "https://oncap.example.org/newsletter"),
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
    history_months = config["history"]["email_engagement_months"]

    seed = config["seeds"]["email"]
    rng = random.Random(seed)
    me = messiness["email_engagement"]

    # Active + Deferred members get emails
    members = [
        m for m in iter_member_census(member_dat_path, layout)
        if m["STATUS_CODE"] in ("A", "D") and m["EMAIL"]   # only members with email
    ]
    logger.info("Members with email (A+D): %d", len(members))

    months = []
    cur = as_of.replace(day=1)
    for _ in range(history_months):
        months.append(cur)
        if cur.month == 1:
            cur = cur.replace(year=cur.year - 1, month=12)
        else:
            cur = cur.replace(month=cur.month - 1)
    months.sort()

    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    total_rows = 0

    for month_start in months:
        if month_start.month == 12:
            next_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_start = month_start.replace(month=month_start.month + 1)
        month_end = next_start - timedelta(days=1)

        out_path = output_dir / f"{plan_code}_EMAIL_ENGAGEMENT_{month_start.strftime('%Y%m')}.csv"

        # Each month: 1 campaign sent to ~all members
        # Plus subscribers might receive multiple emails
        events_this_month = []
        seq = 0

        # Pick a campaign for the month
        campaign_key = rng.choice(list(CAMPAIGNS.keys()))
        campaign_id, campaign_name, click_url = CAMPAIGNS[campaign_key]

        for member in members:
            seq += 1
            send_dt_date = random_date_between(month_start, month_end, rng)
            send_dt = datetime.combine(
                send_dt_date,
                datetime.min.time().replace(
                    hour=rng.randint(7, 14), minute=rng.randint(0, 59),
                ),
            )

            mid = str(member["MEMBER_ID"]).zfill(10)

            # SENT event
            events_this_month.append({
                "event_id": generate_email_event_id(send_dt_date, seq),
                "member_id": mid,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "event_type": "SENT",
                "event_timestamp": send_dt.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                "link_url_clicked": "",
            })

            # 8% bounce
            if roll(me["bounce_rate"], rng):
                seq += 1
                events_this_month.append({
                    "event_id": generate_email_event_id(send_dt_date, seq),
                    "member_id": mid,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "event_type": "BOUNCED",
                    "event_timestamp": (send_dt + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                    "link_url_clicked": "",
                })
                continue

            # DELIVERED (always for non-bounced)
            seq += 1
            events_this_month.append({
                "event_id": generate_email_event_id(send_dt_date, seq),
                "member_id": mid,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "event_type": "DELIVERED",
                "event_timestamp": (send_dt + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                "link_url_clicked": "",
            })

            # OPENED (35%)
            if roll(0.35, rng):
                seq += 1
                open_dt = send_dt + timedelta(minutes=rng.randint(5, 1440))
                events_this_month.append({
                    "event_id": generate_email_event_id(send_dt_date, seq),
                    "member_id": mid,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "event_type": "OPENED",
                    "event_timestamp": open_dt.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                    "link_url_clicked": "",
                })

                # CLICKED (~25% of openers)
                if roll(0.25, rng):
                    seq += 1
                    click_dt = open_dt + timedelta(seconds=rng.randint(5, 600))
                    events_this_month.append({
                        "event_id": generate_email_event_id(send_dt_date, seq),
                        "member_id": mid,
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "event_type": "CLICKED",
                        "event_timestamp": click_dt.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                        "link_url_clicked": click_url,
                    })

            # UNSUBSCRIBE (0.5%)
            if roll(me["unsubscribe_rate"], rng):
                seq += 1
                unsub_dt = send_dt + timedelta(hours=rng.randint(1, 48))
                events_this_month.append({
                    "event_id": generate_email_event_id(send_dt_date, seq),
                    "member_id": mid,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "event_type": "UNSUBSCRIBED",
                    "event_timestamp": unsub_dt.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                    "link_url_clicked": "",
                })

        with CsvWriter(out_path) as w:
            w.write_header(COLUMNS)
            for ev in events_this_month:
                w.write_row(ev)

        files_written += 1
        total_rows += len(events_this_month)
        logger.info("  %s: %d events", out_path.name, len(events_this_month))

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
    print(f"\n=== Email Engagement Generator ===")
    print(f"  Files written:  {stats['files_written']}")
    print(f"  Total events:   {stats['total_rows']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
