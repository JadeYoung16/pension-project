"""
Portal Events Generator — Stage 3c

Generates daily JSONL files of member portal activity over a 90-day window.
Mirrors common web analytics export format (one JSON object per line).

Output:
  data/synthetic/portal_events/ONCAP001_PORTAL_EVENTS_YYYYMMDD.jsonl  × 90 files

Event volume per active member per year (from plan_config.yaml engagement):
  portal_login: 3.5
  statement_view: 1.2
  pension_calculator_use: 0.8
  buyback_quote_request: 0.15  ← buyback leading indicator
  ...

Daily rate ≈ (annual_rate / 365) × active_members ~= 500-700 events/day.

Messiness:
  - 3% missing user_agent
  - 5% null ip_hash (mobile app)
  - 1 in 10000 malformed JSON (skipped from now; emit a sentinel comment)
  - 20% timestamp in UTC
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from upstream_simulators.shared.dates import random_date_between
from upstream_simulators.shared.ids import generate_event_id, generate_session_id, generate_ip_hash
from upstream_simulators.shared.messiness import format_timestamp_with_timezone_drift, maybe_null, roll
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census
from upstream_simulators.shared.writers.jsonl import JsonlWriter


logger = logging.getLogger("portal_event_generator")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "portal_events"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    "Mozilla/5.0 (Linux; Android 12; SM-G991U)",
]

EVENT_PAGES = {
    "portal_login": "/login",
    "portal_logout": "/logout",
    "statement_view": "/statements",
    "pension_calculator_use": "/calculator",
    "buyback_info_page_view": "/buyback/info",
    "buyback_quote_request": "/buyback/quote",
    "beneficiary_page_view": "/beneficiary",
    "document_download": "/documents",
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
    history_months = config["history"]["portal_events_months"]

    history_end = as_of
    history_start = as_of - timedelta(days=history_months * 30)
    logger.info("History window: %s to %s", history_start, history_end)

    seed = config["seeds"]["portal"]
    rng = random.Random(seed)
    me = messiness["portal_events"]
    eng = config["engagement"]

    # Load active members
    active_members = [
        m for m in iter_member_census(member_dat_path, layout)
        if m["STATUS_CODE"] == "A"
    ]
    logger.info("Active members: %d", len(active_members))

    # For each event type, expected total events over history window
    history_days = (history_end - history_start).days
    history_years = history_days / 365.25

    event_totals = {
        "portal_login": int(eng["portal_login_per_year"] * history_years * len(active_members)),
        "statement_view": int(eng["statement_view_per_year"] * history_years * len(active_members)),
        "pension_calculator_use": int(eng["pension_calculator_use_per_year"] * history_years * len(active_members)),
        "buyback_info_page_view": int(eng["buyback_quote_request_per_year"] * 4 * history_years * len(active_members)),
        "buyback_quote_request": int(eng["buyback_quote_request_per_year"] * history_years * len(active_members)),
        "beneficiary_page_view": int(0.3 * history_years * len(active_members)),
        "document_download": int(0.5 * history_years * len(active_members)),
    }
    # Each login → eventual logout (50% of logins)
    event_totals["portal_logout"] = event_totals["portal_login"] // 2

    total_events_planned = sum(event_totals.values())
    logger.info("Planned events: %d", total_events_planned)

    # Generate all events in memory, then bucket by day
    all_events = []
    for event_type, count in event_totals.items():
        for _ in range(count):
            member = rng.choice(active_members)
            event_date = random_date_between(history_start, history_end, rng)
            event_dt = datetime.combine(
                event_date,
                datetime.min.time().replace(
                    hour=rng.randint(7, 22), minute=rng.randint(0, 59),
                    second=rng.randint(0, 59),
                ),
            )
            all_events.append((event_dt, event_type, member))

    # Sort
    all_events.sort(key=lambda e: e[0])

    # Bucket by day
    by_day = {}
    for dt, event_type, member in all_events:
        day_key = dt.date()
        by_day.setdefault(day_key, []).append((dt, event_type, member))

    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    total_rows = 0

    cur_date = history_start
    while cur_date <= history_end:
        events_today = by_day.get(cur_date, [])
        out_path = output_dir / f"{plan_code}_PORTAL_EVENTS_{cur_date.strftime('%Y%m%d')}.jsonl"
        with JsonlWriter(out_path) as w:
            for dt, event_type, member in events_today:
                ip_hash_val = maybe_null(generate_ip_hash(rng), rng, me["ip_hash_null"])
                ua = maybe_null(rng.choice(USER_AGENTS), rng, me["user_agent_missing"])
                ts = format_timestamp_with_timezone_drift(dt, rng, me["timestamp_in_utc"])

                obj = {
                    "event_id": generate_event_id(rng).replace("EVT", "evt_"),
                    "member_id": str(member["MEMBER_ID"]).zfill(10),
                    "event_timestamp": ts,
                    "event_type": event_type,
                    "session_id": generate_session_id(rng),
                    "ip_hash": ip_hash_val,
                    "user_agent": ua,
                    "page_path": EVENT_PAGES.get(event_type, "/"),
                    "referrer": None,
                    "event_properties": {
                        "auth_method": "password" if event_type == "portal_login" else None,
                    },
                }
                # Filter out None auth_method noise
                obj["event_properties"] = {k: v for k, v in obj["event_properties"].items() if v is not None}

                # Malformed JSON injection (1 in 10000)
                if roll(me["malformed_json"], rng):
                    # Write a deliberately broken JSON line
                    bad = json.dumps(obj)[:-3]  # drop closing brace
                    w.write_raw_line(bad)
                else:
                    w.write_row(obj)
                total_rows += 1

        files_written += 1
        cur_date += timedelta(days=1)

    return {
        "files_written": files_written,
        "total_rows": total_rows,
        "active_members": len(active_members),
    }


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
    print(f"\n=== Portal Events Generator ===")
    print(f"  Files written:    {stats['files_written']}")
    print(f"  Total events:     {stats['total_rows']:,}")
    print(f"  Active members:   {stats['active_members']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
