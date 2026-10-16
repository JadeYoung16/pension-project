"""
Portal Events Generator — Stage 3c (web analytics export)

Renders 12 months of daily JSONL exports from the member portal's web
analytics tool:
  - Generic activity (login, statements, calculator, beneficiary, documents)
    for Active members, as before.
  - Buyback page sessions taken from the journey ground truth
    (data/synthetic/_ground_truth/journey_touches.csv): email-click landings,
    organic research visits, and pre-application sessions. Buyback pages are
    therefore visited by eligible members only, and linked to email clicks
    and applications.

Output:
  data/synthetic/portal_events/ONCAP001_PORTAL_EVENTS_YYYYMMDD.jsonl  (one per day)

Realistic, source-driven messiness (messiness_config.yaml: portal_events):
  - Client-dependent timestamps: native app sends UTC ("Z"); web sends local
    time with the correct DST offset (-04:00 / -05:00).
  - Native app sends no IP (ip_hash null); some web events lack a user agent.
  - Files are cut at UTC midnight, so late-evening local events land in the
    next day's file; a small share arrives a further day late.
  - Email-click landings: ~35% happen before login (member_id null; the same
    session may log in later -> identity stitching); Outlook/Hotmail users
    arrive via safelinks (UTMs only recoverable from the encoded referrer);
    UTMs sometimes lost or in a different case.
  - Uptime monitor hits /buyback/info every 5 minutes from 2023-11-01.
  - Tag double-fire: same page recorded twice within a second.
  - Rare malformed JSON lines.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml

from upstream_simulators.shared.ids import generate_event_id, generate_ip_hash, generate_session_id
from upstream_simulators.generators.journey_simulator import add_months


logger = logging.getLogger("portal_event_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_GT_TOUCHES = PROJECT_ROOT / "data" / "synthetic" / "_ground_truth" / "journey_touches.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "portal_events"

LOCAL_TZ = ZoneInfo("America/Toronto")

WEB_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    "Mozilla/5.0 (Linux; Android 12; SM-G991U)",
]
APP_AGENTS = ["ONCAPMobile/3.4.1 (iOS 17.0)", "ONCAPMobile/3.4.0 (Android 13)"]
MONITOR_AGENT = "UptimeMonitor/2.0 (+https://status.oncap.example.org)"

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
GT_PAGE_TO_EVENT = {
    "portal_login": "portal_login",
    "buyback_info": "buyback_info_page_view",
    "buyback_quote": "buyback_quote_request",
}


# -----------------------------------------------------------------------------
# Session / event helpers
# -----------------------------------------------------------------------------

def pick_client(rng) -> tuple[str, str]:
    r = rng.random()
    if r < 0.25:
        return "app", rng.choice(APP_AGENTS)
    return "web", rng.choice(WEB_AGENTS)


def fmt_ts(local_naive: datetime, client: str) -> str:
    aware = local_naive.replace(tzinfo=LOCAL_TZ)
    if client == "app":
        return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return aware.isoformat(timespec="seconds")          # e.g. 2023-07-05T09:12:03-04:00


def utc_date(local_naive: datetime) -> date:
    return local_naive.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc).date()


def make_event(rng, me, *, member_id, local_ts, event_type, session_id, client, ua,
               ip_hash, referrer=None, props=None) -> dict:
    if client == "web" and rng.random() < me["user_agent_missing"]:
        ua = None
    p = dict(props or {})
    if event_type == "portal_login":
        p["auth_method"] = "password"
    return {
        "_local": local_ts, "_client": client,
        "event_id": generate_event_id(rng).replace("EVT", "evt_"),
        "member_id": member_id,
        "event_timestamp": fmt_ts(local_ts, client),
        "event_type": event_type,
        "session_id": session_id,
        "ip_hash": None if client == "app" else ip_hash,
        "user_agent": ua,
        "page_path": EVENT_PAGES[event_type],
        "referrer": referrer,
        "event_properties": p,
    }


# -----------------------------------------------------------------------------
# Generic (non-buyback) activity
# -----------------------------------------------------------------------------

def render_generic(active_ids, start, end, config, messiness, rng) -> list[dict]:
    eng = config["engagement"]
    me = messiness["portal_events"]
    years = ((end - start).days + 1) / 365.25
    n = len(active_ids)
    totals = {
        "portal_login": int(eng["portal_login_per_year"] * years * n),
        "statement_view": int(eng["statement_view_per_year"] * years * n),
        "pension_calculator_use": int(eng["pension_calculator_use_per_year"] * years * n),
        "beneficiary_page_view": int(0.3 * years * n),
        "document_download": int(0.5 * years * n),
    }
    totals["portal_logout"] = totals["portal_login"] // 2
    span = (end - start).days
    events = []
    for event_type, count in totals.items():
        for _ in range(count):
            mid = rng.choice(active_ids)
            d = start + timedelta(days=rng.randint(0, span))
            ts = datetime.combine(d, datetime.min.time()).replace(
                hour=rng.randint(7, 23), minute=rng.randint(0, 59), second=rng.randint(0, 59))
            client, ua = pick_client(rng)
            events.append(make_event(rng, me, member_id=mid, local_ts=ts, event_type=event_type,
                                     session_id=generate_session_id(rng), client=client, ua=ua,
                                     ip_hash=generate_ip_hash(rng)))
    return events


# -----------------------------------------------------------------------------
# Buyback sessions from ground truth
# -----------------------------------------------------------------------------

def landing_attribution(rng, me, config, email_domain: str) -> tuple[dict, str | None]:
    """Return (event_properties, referrer) for an email-click landing."""
    c = config["campaign"]
    campaign = c["utm_campaign"]
    if rng.random() < me["utm_case_variant_rate"]:
        campaign = rng.choice([campaign.upper(), campaign.title()])
    tagged = f"{c['landing_url']}?utm_source=email&utm_medium=email&utm_campaign={campaign}"
    if rng.random() < me["utm_lost_rate"]:
        return {"page_location": c["landing_url"]}, None
    if email_domain in me["safelinks_domains"]:
        safelink = ("https://nam11.safelinks.protection.outlook.com/?url="
                    + quote(tagged, safe="") + "&data=05%7C01%7C&reserved=0")
        return {"page_location": c["landing_url"]}, safelink
    return {"page_location": tagged}, None


def render_gt_sessions(gt_path: Path, domains: dict, start, end, config, messiness, rng) -> list[dict]:
    me = messiness["portal_events"]
    events = []
    with gt_path.open(newline="", encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["channel"] != "portal":
                continue
            ts = datetime.fromisoformat(t["ts_local"])
            if not (start <= ts.date() <= end):
                continue
            mid = t["member_id"]
            pages = t["detail"].split(">")
            sid = generate_session_id(rng)
            client, ua = pick_client(rng)
            ip = generate_ip_hash(rng)
            props, ref = {}, None
            anonymous = False
            if t["source"] == "email_click":
                client, ua = "web", rng.choice(WEB_AGENTS)    # links open in a browser
                props, ref = landing_attribution(rng, me, config, domains.get(mid, ""))
                anonymous = rng.random() < me["anonymous_landing_rate"]
            logged_in = not anonymous
            cur = ts
            for i, page in enumerate(pages):
                event_type = GT_PAGE_TO_EVENT[page]
                if event_type == "portal_login":
                    logged_in = True
                events.append(make_event(
                    rng, me, member_id=mid if logged_in else None, local_ts=cur,
                    event_type=event_type, session_id=sid, client=client, ua=ua, ip_hash=ip,
                    referrer=ref if i == 0 else None, props=props if i == 0 else None))
                cur += timedelta(seconds=rng.randint(8, 180))
    return events


def render_monitor(start, end, messiness) -> list[dict]:
    me = messiness["portal_events"]
    first = max(start, date.fromisoformat(me["uptime_monitor_start"]))
    step = timedelta(minutes=me["uptime_monitor_interval_minutes"])
    rng = random.Random(7)
    ts = datetime.combine(first, datetime.min.time())
    stop = datetime.combine(end + timedelta(days=1), datetime.min.time())
    out = []
    ip = "sha256:00monitor00ffee"
    while ts < stop:
        out.append(make_event(rng, me, member_id=None, local_ts=ts, event_type="buyback_info_page_view",
                              session_id=generate_session_id(rng), client="monitor", ua=MONITOR_AGENT,
                              ip_hash=ip))
        ts += step
    return out


# -----------------------------------------------------------------------------
# Writing (export-level messiness: UTC file cut, late rows, double-fire, bad JSON)
# -----------------------------------------------------------------------------

def write_files(events, start, end, config, messiness, out_dir: Path, rng) -> dict:
    me = messiness["portal_events"]
    plan = config["plan"]["plan_code"]
    by_file = defaultdict(list)
    stats = {"rows": 0, "double_fire": 0, "late": 0, "malformed": 0, "files": 0}
    for e in events:
        file_day = utc_date(e["_local"])
        if rng.random() < me["late_file_rate"]:
            file_day += timedelta(days=1)
            stats["late"] += 1
        by_file[file_day].append(e)
        if e["_client"] != "monitor" and rng.random() < me["double_fire_rate"]:
            dup = dict(e)
            dup["event_id"] = generate_event_id(rng).replace("EVT", "evt_")
            by_file[file_day].append(dup)
            stats["double_fire"] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    d = start
    while d <= end + timedelta(days=1):
        rows = sorted(by_file.get(d, []), key=lambda e: e["_local"])
        path = out_dir / f"{plan}_PORTAL_EVENTS_{d.strftime('%Y%m%d')}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for e in rows:
                obj = {k: v for k, v in e.items() if not k.startswith("_")}
                line = json.dumps(obj)
                if rng.random() < me["malformed_json"]:
                    line = line[:-3]
                    stats["malformed"] += 1
                f.write(line + "\n")
                stats["rows"] += 1
        stats["files"] += 1
        d += timedelta(days=1)
    return stats


def render_all(active_ids, domains, config, messiness, gt_path: Path, out_dir: Path) -> dict:
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    start = add_months(as_of.replace(day=1), -(config["history"]["portal_events_months"] - 1))
    end = as_of
    if not gt_path.exists():
        raise FileNotFoundError(f"{gt_path} not found — run stage 2b (journey_simulator) first.")
    rng = random.Random(config["seeds"]["portal"])
    logger.info("History window: %s to %s, active members: %d", start, end, len(active_ids))
    events = render_generic(active_ids, start, end, config, messiness, rng)
    gt_events = render_gt_sessions(gt_path, domains, start, end, config, messiness, rng)
    monitor = render_monitor(start, end, messiness)
    stats = write_files(events + gt_events + monitor, start, end, config, messiness, out_dir, rng)
    stats.update(generic=len(events), buyback_sessions_events=len(gt_events), monitor=len(monitor))
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

    from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
    from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census

    config = yaml.safe_load(args.config.read_text())
    messiness = yaml.safe_load(args.messiness.read_text())
    layout = FixedWidthLayout.from_yaml(args.layout)
    active_ids, domains = [], {}
    for m in iter_member_census(args.member_dat, layout):
        mid = str(m["MEMBER_ID"]).zfill(10)
        if m["STATUS_CODE"] == "A":
            active_ids.append(mid)
        if m["EMAIL"]:
            domains[mid] = m["EMAIL"].strip().split("@")[-1].lower()
    s = render_all(active_ids, domains, config, messiness, args.gt_touches, args.output_dir)
    print("\n=== Portal Events Generator ===")
    print(f"  Files written:        {s['files']}")
    print(f"  Total rows:           {s['rows']:,}")
    print(f"  Generic events:       {s['generic']:,}")
    print(f"  Buyback session evts: {s['buyback_sessions_events']:,}")
    print(f"  Uptime monitor hits:  {s['monitor']:,}")
    print(f"  Double-fire / late / malformed: {s['double_fire']:,} / {s['late']:,} / {s['malformed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
