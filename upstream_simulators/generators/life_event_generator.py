"""
Life Events Generator — Stage 3b (pension admin system extract)

Generates monthly batches of life events from 2022-02 through 2024-01.
Most important: buyback application chains (BBK_APP -> QUOTE -> APPROVED -> COMPLETE).

Output:
  data/synthetic/life_events/ONCAP001_LIFE_EVENTS_YYYYMM.TXT  x 24 files

Each file is pipe-delimited UTF-8 with column header on line 1, then events.

Business logic:
  WHO applies, WHEN, through WHICH channel, and the window / cost / payment /
  outcome details all come from the journey ground truth
  (data/synthetic/_ground_truth/journey_members.csv, stage 2b), so applications
  are linked to eligibility, the campaign and portal visits. This generator only
  renders the admin system's view of each application:
    BBK_APP             : event_date = date received; for paper (MAIL)
                          applications event_timestamp = when it was keyed in,
                          7-21 days later (data-entry backlog)
    BBK_QUOTE           : +5 business days after entry (system)
    BBK_APPROVED        : +14 business days after entry (system)
    BBK_COMPLETE        : lump sum next day, or with the last installment
    BBK_CANCELLED       : within 7 days
    BBK_INSTALLMENT_PAY : monthly during installment period
  Re-applications: a member who cancelled re-applies 10-40 days later
  (a second BBK_APP chain for the same member).
  Non-buyback events (BENE_UPD, MARITAL, ADDR_CHG) are unchanged.

Messiness:
  - Legacy system stamps every local time with a fixed -05:00 offset (no DST);
    ~10% of rows come through an integration that writes UTC ("Z").
  - Garbage free-text notes.
  - leave_end_date is the admin system's own value: blank or in the future
    for the defective census rows.
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

from upstream_simulators.shared.dates import add_business_days, random_date_between
from upstream_simulators.shared.ids import generate_event_id
from upstream_simulators.shared.messiness import (
    format_timestamp_with_timezone_drift, maybe_garbage_notes, roll,
)
from upstream_simulators.shared.writers.delimited import PipeDelimitedWriter


logger = logging.getLogger("life_event_generator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_GT_MEMBERS = PROJECT_ROOT / "data" / "synthetic" / "_ground_truth" / "journey_members.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "life_events"

# Output column order (docs/03_record_layouts.md File 4) — unchanged
OUTPUT_COLUMNS = [
    "event_id", "member_id", "employer_id", "event_type_code", "event_date",
    "event_timestamp", "buyback_category_code", "buyback_service_years",
    "leave_end_date", "months_since_eligibility", "is_within_window",
    "is_open_option", "member_cost", "employer_cost", "total_cost",
    "payment_method", "installment_months", "event_status", "channel_code", "notes",
]


@dataclass
class MemberBuybackPlan:
    member_id: str
    employer_id: str
    application_date: date          # date received
    entered_date: date              # date keyed into the admin system
    channel: str                    # PORTAL or MAIL
    buyback_category: str
    buyback_service_years: float
    leave_end_date: str             # admin system value (may be blank / future)
    months_since_eligibility: int
    is_within_window: bool
    payment_method: str
    installment_months: Optional[int]
    chain_outcome: str              # normal / rejected / cancelled / abandoned
    member_cost: float
    employer_cost: float
    total_cost: float


# -----------------------------------------------------------------------------
# Plans from ground truth
# -----------------------------------------------------------------------------

def _wchoice(d: dict, rng):
    keys = list(d)
    return rng.choices(keys, weights=[d[k] for k in keys], k=1)[0]


def load_plans(gt_path: Path, census: dict, config: dict, rng, history_end: date) -> list[MemberBuybackPlan]:
    plans = []
    with gt_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["applied_on"]:
                continue
            c = census.get(r["member_id"], {})
            inst = int(r["installment_months"]) if r["installment_months"] else None
            plan = MemberBuybackPlan(
                member_id=r["member_id"],
                employer_id=r["employer_id"],
                application_date=date.fromisoformat(r["applied_on"]),
                entered_date=date.fromisoformat(r["entered_date"]),
                channel=r["channel"],
                buyback_category=r["buyback_category"],
                buyback_service_years=float(c.get("ELIGIBLE_BUYBACK_SERVICE") or 0.0),
                leave_end_date=c["LAST_BUYBACK_LEAVE_END_DATE"].isoformat()
                if c.get("LAST_BUYBACK_LEAVE_END_DATE") else "",
                months_since_eligibility=int(r["months_since_eligibility"]),
                is_within_window=r["is_within_window"] == "Y",
                payment_method=r["payment_method"],
                installment_months=inst,
                chain_outcome=r["chain_outcome"],
                member_cost=float(r["member_cost"]),
                employer_cost=float(r["employer_cost"]),
                total_cost=float(r["total_cost"]),
            )
            plans.append(plan)
            if r["reapply_date"]:
                d = date.fromisoformat(r["reapply_date"])
                if d <= history_end:
                    outcomes = {k: v for k, v in config["buyback"]["chain_outcomes"].items() if k != "cancelled"}
                    lag = (plan.entered_date - plan.application_date).days
                    plans.append(replace(plan, application_date=d,
                                         entered_date=d + timedelta(days=lag),
                                         months_since_eligibility=plan.months_since_eligibility + (d - plan.application_date).days // 30,
                                         chain_outcome=_wchoice(outcomes, rng)))
    return plans


# -----------------------------------------------------------------------------
# Event rows
# -----------------------------------------------------------------------------

def _common_buyback_fields(plan: MemberBuybackPlan) -> dict:
    return {
        "buyback_category_code": plan.buyback_category,
        "buyback_service_years": f"{plan.buyback_service_years:.2f}",
        "leave_end_date": plan.leave_end_date,
        "months_since_eligibility": plan.months_since_eligibility,
        "is_within_window": "Y" if plan.is_within_window else "N",
        "is_open_option": "N" if plan.is_within_window else "Y",
        "member_cost": f"{plan.member_cost:.2f}",
        "employer_cost": f"{plan.employer_cost:.2f}",
        "total_cost": f"{plan.total_cost:.2f}",
        "payment_method": plan.payment_method,
        "installment_months": plan.installment_months or "",
    }


def _make_event_row(plan, event_type, event_dt, status, channel, rng, messiness,
                    notes="", event_date: Optional[date] = None) -> dict:
    me = messiness["life_events"]
    row = {
        "event_id": generate_event_id(rng),
        "member_id": plan.member_id,
        "employer_id": plan.employer_id,
        "event_type_code": event_type,
        "event_date": (event_date or event_dt.date()).isoformat(),
        "event_timestamp": format_timestamp_with_timezone_drift(event_dt, rng, me["timezone_mixed"]),
        "event_status": status,
        "channel_code": channel,
        "notes": maybe_garbage_notes(notes, rng, me["notes_garbage_text"]) if notes else "",
    }
    row.update(_common_buyback_fields(plan))
    return row


def _at(d: date, hour: int, rng) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=rng.randint(0, 59))


def generate_buyback_chain(plan: MemberBuybackPlan, rng, messiness, history_end: date) -> list[dict]:
    events = []
    # APP: received on application_date; keyed in on entered_date
    entered_dt = _at(plan.entered_date, rng.randint(8, 17), rng)
    if plan.entered_date > history_end:
        return events            # still sitting in the paper backlog at extract time
    events.append(_make_event_row(plan, "BBK_APP", entered_dt, "SUBMITTED", plan.channel,
                                  rng, messiness, event_date=plan.application_date))

    if plan.chain_outcome == "cancelled":
        cancel_dt = entered_dt + timedelta(days=rng.randint(1, 7))
        if cancel_dt.date() <= history_end:
            events.append(_make_event_row(plan, "BBK_CANCELLED", cancel_dt, "CANCELLED", plan.channel,
                                          rng, messiness, notes="Member cancelled application"))
        return events

    quote_date = add_business_days(plan.entered_date, 5)
    if quote_date > history_end:
        return events
    events.append(_make_event_row(plan, "BBK_QUOTE", _at(quote_date, 10, rng), "QUOTED", "SYSTEM", rng, messiness))
    if plan.chain_outcome == "abandoned":
        return events

    approved_date = add_business_days(plan.entered_date, 14)
    if approved_date > history_end:
        return events
    approved_dt = _at(approved_date, 9, rng)
    if plan.chain_outcome == "rejected":
        events.append(_make_event_row(plan, "BBK_APPROVED", approved_dt, "REJECTED", "SYSTEM",
                                      rng, messiness, notes="Insufficient documentation"))
        return events
    events.append(_make_event_row(plan, "BBK_APPROVED", approved_dt, "APPROVED", "SYSTEM", rng, messiness))

    if plan.payment_method == "LUMP_SUM":
        complete_dt = approved_dt + timedelta(days=1)
        if complete_dt.date() <= history_end:
            events.append(_make_event_row(plan, "BBK_COMPLETE", complete_dt, "COMPLETED", "SYSTEM", rng, messiness))
        return events

    monthly = plan.member_cost / plan.installment_months
    pay_date = approved_date + timedelta(days=30)
    for i in range(plan.installment_months):
        if pay_date > history_end:
            break
        pay_dt = datetime.combine(pay_date, datetime.min.time()).replace(hour=2)
        inst = replace(plan, member_cost=round(monthly, 2), total_cost=round(monthly, 2), employer_cost=0.0)
        events.append(_make_event_row(inst, "BBK_INSTALLMENT_PAY", pay_dt, "COMPLETED", "SYSTEM", rng, messiness,
                                      notes=f"Installment {i+1} of {plan.installment_months}"))
        if i == plan.installment_months - 1:
            events.append(_make_event_row(plan, "BBK_COMPLETE", pay_dt + timedelta(seconds=1), "COMPLETED",
                                          "SYSTEM", rng, messiness, notes="Final installment processed"))
        pay_date += timedelta(days=30)
    return events


# -----------------------------------------------------------------------------
# Non-buyback events (unchanged behaviour)
# -----------------------------------------------------------------------------

def generate_non_buyback_events(members, history_start, history_end, rng, messiness) -> list[dict]:
    events = []
    months = ((history_end.year - history_start.year) * 12 + history_end.month - history_start.month + 1)
    me = messiness["life_events"]
    blank = {k: "" for k in ["buyback_category_code", "buyback_service_years", "leave_end_date",
                             "months_since_eligibility", "is_within_window", "is_open_option",
                             "member_cost", "employer_cost", "total_cost", "payment_method",
                             "installment_months"]}
    for event_type, monthly_count, note in [("BENE_UPD", 40, "Beneficiary update"),
                                            ("MARITAL", 15, "Marital status change"),
                                            ("ADDR_CHG", 100, "Address change")]:
        for _ in range(monthly_count * months):
            m = rng.choice(members)
            d = random_date_between(history_start, history_end, rng)
            dt = datetime.combine(d, datetime.min.time()).replace(hour=rng.randint(7, 22), minute=rng.randint(0, 59))
            row = {
                "event_id": generate_event_id(rng),
                "member_id": str(m["MEMBER_ID"]).zfill(10),
                "employer_id": m["EMPLOYER_ID"],
                "event_type_code": event_type,
                "event_date": d.isoformat(),
                "event_timestamp": format_timestamp_with_timezone_drift(dt, rng, me["timezone_mixed"]),
                "event_status": "COMPLETED",
                "channel_code": rng.choice(["PORTAL", "MAIL", "PHONE", "ADVISOR"]),
                "notes": note if not roll(me["notes_garbage_text"], rng) else "",
            }
            row.update(blank)
            events.append(row)
    return events


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------

def history_window(config) -> tuple[date, date]:
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    n = config["history"]["life_events_months"]
    y, m = as_of.year, as_of.month - n + 1
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), as_of


def render_all(members, config, messiness, gt_path: Path, output_dir: Path) -> dict:
    if not gt_path.exists():
        raise FileNotFoundError(f"{gt_path} not found — run stage 2b (journey_simulator) first.")
    plan_code = config["plan"]["plan_code"]
    history_start, history_end = history_window(config)
    rng = random.Random(config["seeds"]["life_event"])
    census = {str(m["MEMBER_ID"]).zfill(10): m for m in members}

    plans = load_plans(gt_path, census, config, rng, history_end)
    buyback_events, outcomes, channels = [], defaultdict(int), defaultdict(int)
    for p in plans:
        outcomes[p.chain_outcome] += 1
        channels[p.channel] += 1
        buyback_events.extend(generate_buyback_chain(p, rng, messiness, history_end))
    non_buyback = generate_non_buyback_events(members, history_start, history_end, rng, messiness)

    buckets = defaultdict(list)
    for ev in buyback_events + non_buyback:
        buckets[ev["event_date"][:7].replace("-", "")].append(ev)

    output_dir.mkdir(parents=True, exist_ok=True)
    files = 0
    y, m = history_start.year, history_start.month
    while date(y, m, 1) <= history_end:
        key = f"{y:04d}{m:02d}"
        rows = sorted(buckets.get(key, []), key=lambda e: (e["event_date"], e["event_timestamp"]))
        with PipeDelimitedWriter(output_dir / f"{plan_code}_LIFE_EVENTS_{key}.TXT") as w:
            w.write_column_header(OUTPUT_COLUMNS)
            for ev in rows:
                w.write_row(ev, OUTPUT_COLUMNS)
        files += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return {"files": files, "plans": len(plans), "buyback_rows": len(buyback_events),
            "non_buyback_rows": len(non_buyback), "outcomes": dict(outcomes), "channels": dict(channels)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate ONCAP life events.")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    ap.add_argument("--gt-members", type=Path, default=DEFAULT_GT_MEMBERS)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
    from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census

    config = yaml.safe_load(args.config.read_text())
    messiness = yaml.safe_load(args.messiness.read_text())
    layout = FixedWidthLayout.from_yaml(args.layout)
    members = list(iter_member_census(args.member_dat, layout))
    s = render_all(members, config, messiness, args.gt_members, args.output_dir)

    print("\n" + "=" * 70)
    print("Life Events Generator — Summary")
    print("=" * 70)
    print(f"  Files written:           {s['files']}")
    print(f"  Buyback applications:    {s['plans']:,}  (incl. re-applications)")
    print(f"  Channels:                {s['channels']}")
    print(f"  Chain outcomes:          {s['outcomes']}")
    print(f"  Buyback event rows:      {s['buyback_rows']:,}")
    print(f"  Non-buyback event rows:  {s['non_buyback_rows']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
