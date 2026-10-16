"""
Email Engagement Generator — Stage 3f (ESP event export)

Renders 12 monthly CSV exports from the email service provider (ESP):
  - Monthly general campaigns (newsletter / statement / retirement tips) to
    Active + Deferred members with an email address.
  - The randomized buyback campaign, taken verbatim from the journey ground
    truth (data/synthetic/_ground_truth/journey_touches.csv) so email outcomes
    stay linked to portal sessions and applications.

Output:
  data/synthetic/email_engagement/ONCAP001_EMAIL_ENGAGEMENT_YYYYMM.csv  x 12

Realistic, source-driven messiness (messiness_config.yaml: email_engagement):
  - Timestamps are UTC ("Z") — the ESP's convention, not local time.
  - Apple Mail Privacy Protection: a fixed set of members (~17%) "opens"
    every delivered email within 60s (machine opens, ~40% of all opens).
  - Click with no OPENED event (images blocked -> no open pixel).
  - Security gateway scanners "click" within seconds of delivery.
  - Webhook retries: exact duplicate rows, same event_id.
  - Bounces split hard/soft; a share of hard-bounced addresses is emailed
    again (suppression list sync lag).
  - Unsubscribed members occasionally emailed later (preference not synced);
    the buyback campaign is CRM-triggered and ignores ESP suppression.
  - Schema change on schema_change_date: files from that month on add a
    `bounce_type` column and reorder columns (ESP platform upgrade).
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from upstream_simulators.shared.ids import generate_email_event_id
from upstream_simulators.generators.journey_simulator import add_months, stable_frac


logger = logging.getLogger("email_engagement_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_GT_TOUCHES = PROJECT_ROOT / "data" / "synthetic" / "_ground_truth" / "journey_touches.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "email_engagement"

LOCAL_TZ = ZoneInfo("America/Toronto")

COLUMNS_OLD = [
    "event_id", "member_id", "campaign_id", "campaign_name",
    "event_type", "event_timestamp", "link_url_clicked",
]
COLUMNS_NEW = [
    "event_id", "event_type", "event_timestamp", "member_id",
    "campaign_id", "campaign_name", "link_url_clicked", "bounce_type",
]

# General (non-buyback) campaigns. The old "Q1 2024 Buyback Reminder" was
# removed: an untracked buyback email to everyone would contaminate the
# experiment's control group.
GENERAL_CAMPAIGNS = [
    ("CAMP_NEWSLETTER", "ONCAP Member Newsletter", "https://oncap.example.org/newsletter"),
    ("CAMP_ANNUAL_STMT", "Annual Statement Available", "https://oncap.example.org/statements"),
    ("CAMP_RETIRE_TIPS", "Plan Your Retirement", "https://oncap.example.org/retirement-tips"),
]
GENERAL_HUMAN_OPEN = 0.25
GENERAL_CLICK_GIVEN_OPEN = 0.15
CLICK_WITHOUT_OPEN = 0.08


def to_utc(local_naive: datetime) -> str:
    """Local America/Toronto wall time (DST-aware) -> ESP UTC string."""
    aware = local_naive.replace(tzinfo=LOCAL_TZ)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_starts(as_of: date, n: int) -> list[date]:
    first = as_of.replace(day=1)
    return [add_months(first, -k) for k in range(n - 1, -1, -1)]


# -----------------------------------------------------------------------------
# General campaigns (ESP-managed lists, with ESP suppression)
# -----------------------------------------------------------------------------

def render_general(members, months, as_of, config, messiness, rng) -> list[dict]:
    me = messiness["email_engagement"]
    share = me["apple_mpp_member_share"]
    events: list[dict] = []
    suppressed_bounce: set[str] = set()
    unsubscribed: set[str] = set()

    for month_start in months:
        camp_id, camp_name, url = rng.choice(GENERAL_CAMPAIGNS)
        send_day = month_start + timedelta(days=rng.randint(1, 10))
        for m in members:
            mid = m["member_id"]
            if mid in suppressed_bounce and rng.random() >= me["suppression_lag_resend"]:
                continue
            if mid in unsubscribed and rng.random() >= me["unsub_not_honored"]:
                continue
            sent = datetime.combine(send_day, datetime.min.time()).replace(
                hour=rng.randint(7, 14), minute=rng.randint(0, 59), second=rng.randint(0, 59))

            def ev(kind, ts, link="", bounce=""):
                events.append({"member_id": mid, "campaign_id": camp_id, "campaign_name": camp_name,
                               "event_type": kind, "ts_local": ts, "link_url_clicked": link,
                               "bounce_type": bounce})

            ev("SENT", sent)
            if rng.random() < me["bounce_rate"]:
                hard = rng.random() < me["hard_bounce_share"]
                ev("BOUNCED", sent + timedelta(minutes=2), bounce="hard" if hard else "soft")
                if hard:
                    suppressed_bounce.add(mid)
                continue
            delivered = sent + timedelta(minutes=1)
            ev("DELIVERED", delivered)
            if stable_frac("mpp:" + mid) < share:
                ev("OPENED", delivered + timedelta(seconds=rng.randint(1, 60)))
            if rng.random() < me["security_scanner_click_rate"]:
                ev("CLICKED", delivered + timedelta(seconds=rng.randint(1, 30)), url)
            if rng.random() < GENERAL_HUMAN_OPEN:
                opened = delivered + timedelta(minutes=rng.randint(5, 3 * 24 * 60))
                clicked = rng.random() < GENERAL_CLICK_GIVEN_OPEN
                if not (clicked and rng.random() < CLICK_WITHOUT_OPEN):
                    ev("OPENED", opened)
                if clicked:
                    ev("CLICKED", opened + timedelta(seconds=rng.randint(5, 600)), url)
            if rng.random() < me["unsubscribe_rate"]:
                unsubscribed.add(mid)
                ev("UNSUBSCRIBED", sent + timedelta(hours=rng.randint(1, 48)))
    return [e for e in events if e["ts_local"].date() <= as_of]


# -----------------------------------------------------------------------------
# Buyback campaign from ground truth
# -----------------------------------------------------------------------------

def render_campaign(gt_path: Path, config) -> list[dict]:
    c = config["campaign"]
    events = []
    with gt_path.open(newline="", encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["channel"] != "email":
                continue
            kind = t["touch_type"]
            events.append({
                "member_id": t["member_id"], "campaign_id": c["campaign_id"],
                "campaign_name": c["campaign_name"], "event_type": kind,
                "ts_local": datetime.fromisoformat(t["ts_local"]),
                "link_url_clicked": t["detail"] if kind == "CLICKED" else "",
                "bounce_type": t["detail"] if kind == "BOUNCED" else "",
            })
    return events


# -----------------------------------------------------------------------------
# Write monthly files (duplicates + schema change applied here: export-level)
# -----------------------------------------------------------------------------

def write_files(events, months, config, messiness, out_dir: Path, rng) -> dict:
    me = messiness["email_engagement"]
    plan = config["plan"]["plan_code"]
    schema_change = date.fromisoformat(me["schema_change_date"])
    by_month = defaultdict(list)
    for e in events:
        by_month[e["ts_local"].strftime("%Y%m")].append(e)

    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {"files": 0, "rows": 0, "duplicates": 0, "new_schema_files": 0}
    for month_start in months:
        key = month_start.strftime("%Y%m")
        rows = sorted(by_month.get(key, []), key=lambda e: (e["ts_local"], e["member_id"]))
        # Export generated after month end -> new schema once the upgrade is live
        new_schema = month_start >= schema_change.replace(day=1)
        cols = COLUMNS_NEW if new_schema else COLUMNS_OLD
        path = out_dir / f"{plan}_EMAIL_ENGAGEMENT_{key}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            seq = 0
            for e in rows:
                seq += 1
                rec = {
                    "event_id": generate_email_event_id(e["ts_local"].date(), seq),
                    "member_id": e["member_id"], "campaign_id": e["campaign_id"],
                    "campaign_name": e["campaign_name"], "event_type": e["event_type"],
                    "event_timestamp": to_utc(e["ts_local"]),
                    "link_url_clicked": e["link_url_clicked"], "bounce_type": e["bounce_type"],
                }
                line = [rec[c] for c in cols]
                w.writerow(line)
                stats["rows"] += 1
                if rng.random() < me["webhook_duplicate_rate"]:       # webhook retry
                    w.writerow(line)
                    stats["rows"] += 1
                    stats["duplicates"] += 1
        stats["files"] += 1
        stats["new_schema_files"] += int(new_schema)
        logger.info("  %s: %d events%s", path.name, len(rows), " (new schema)" if new_schema else "")
    return stats


def generate(config_path, messiness_path, layout_path, member_dat_path, gt_path, output_dir) -> dict:
    from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
    from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census

    config = yaml.safe_load(Path(config_path).read_text())
    messiness = yaml.safe_load(Path(messiness_path).read_text())
    layout = FixedWidthLayout.from_yaml(layout_path)
    members = [
        {"member_id": str(m["MEMBER_ID"]).zfill(10)}
        for m in iter_member_census(member_dat_path, layout)
        if m["STATUS_CODE"] in ("A", "D") and m["EMAIL"]
    ]
    return render_all(members, config, messiness, Path(gt_path), Path(output_dir))


def render_all(members, config, messiness, gt_path: Path, output_dir: Path) -> dict:
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    months = month_starts(as_of, config["history"]["email_engagement_months"])
    rng = random.Random(config["seeds"]["email"])
    logger.info("Members with email (A+D): %d", len(members))
    if not gt_path.exists():
        raise FileNotFoundError(f"{gt_path} not found — run stage 2b (journey_simulator) first.")
    events = render_general(members, months, as_of, config, messiness, rng)
    events += render_campaign(gt_path, config)
    stats = write_files(events, months, config, messiness, output_dir, rng)
    stats["members"] = len(members)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    ap.add_argument("--gt-touches", type=Path, default=DEFAULT_GT_TOUCHES)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    s = generate(args.config, args.messiness, args.layout, args.member_dat, args.gt_touches, args.output_dir)
    print("\n=== Email Engagement Generator ===")
    print(f"  Members with email:   {s['members']:,}")
    print(f"  Files written:        {s['files']}  (new schema: {s['new_schema_files']})")
    print(f"  Total rows:           {s['rows']:,}  (webhook duplicates: {s['duplicates']:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
