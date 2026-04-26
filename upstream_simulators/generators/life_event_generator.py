"""
Life Events Generator — Stage 3b

Generates monthly batches of life events from 2022-02 through 2024-01.
Most important: buyback application chains (BBK_APP → QUOTE → APPROVED → COMPLETE).

Output:
  data/synthetic/life_events/ONCAP001_LIFE_EVENTS_YYYYMM.TXT  × 24 files

Each file is pipe-delimited UTF-8 with column header on line 1, then events.

Business logic (from docs/01_plan_design_specification.md §5):
  1. Load active+deferred members from latest member census
  2. Filter to those with eligible_buyback_service > 0 (~9,500 members)
  3. For each eligible member, decide:
     a. Will they apply at all? (propensity model based on age/salary/sex)
     b. When? (random month in the 24-month history)
     c. Within window or open option? (70% / 30%)
     d. Lump sum or installment? (40% / 60%)
     e. What's the outcome? (85% complete / 5% rejected / 3% cancelled / 7% abandoned)
  4. For each "will apply" member, generate event chain split across months
  5. Also generate non-buyback events: BENE_UPD, MARITAL, ADDR_CHG (random monthly)

Event types and timing:
  BBK_APP           : member-initiated, on chosen application date
  BBK_QUOTE         : +5 business days (system)
  BBK_APPROVED      : +14 business days from APP (system)
  BBK_COMPLETE      : same day as APPROVED (lump) or last installment (installment)
  BBK_CANCELLED     : 3% rate, between APP and APPROVED
  BBK_INSTALLMENT_PAY : monthly during installment period
  BENE_UPD / MARITAL / ADDR_CHG : independent random events

Cost calculation:
  Within window: member 3% + employer 3% of (salary_at_leave × buyback_years)
  Open option:   member 100% × (salary × buyback_years × 6%) × (1 + premium 0.4-0.6)
                 employer 0
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
from typing import Optional

import yaml

from upstream_simulators.shared.dates import (
    add_business_days, random_date_between,
)
from upstream_simulators.shared.ids import generate_event_id
from upstream_simulators.shared.messiness import (
    format_timestamp_with_timezone_drift, maybe_garbage_notes, roll,
)
from upstream_simulators.shared.writers.delimited import PipeDelimitedWriter
from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census


logger = logging.getLogger("life_event_generator")


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "life_events"


# -----------------------------------------------------------------------------
# Output column order (from docs/03_record_layouts.md File 4)
# -----------------------------------------------------------------------------

OUTPUT_COLUMNS = [
    "event_id",
    "member_id",
    "employer_id",
    "event_type_code",
    "event_date",
    "event_timestamp",
    "buyback_category_code",
    "buyback_service_years",
    "leave_end_date",
    "months_since_eligibility",
    "is_within_window",
    "is_open_option",
    "member_cost",
    "employer_cost",
    "total_cost",
    "payment_method",
    "installment_months",
    "event_status",
    "channel_code",
    "notes",
]


# -----------------------------------------------------------------------------
# Member-level "buyback decision" structure
# -----------------------------------------------------------------------------

@dataclass
class MemberBuybackPlan:
    """Pre-computed plan: when/how this member will buyback (if at all)."""
    member_id: str
    employer_id: str
    application_date: date
    buyback_category: str
    buyback_service_years: float
    salary_at_leave: float
    leave_end_date: date
    months_since_eligibility: int
    is_within_window: bool
    payment_method: str         # LUMP_SUM or INSTALLMENT
    installment_months: Optional[int]
    chain_outcome: str          # normal / rejected / cancelled / abandoned
    member_cost: float
    employer_cost: float
    total_cost: float


# -----------------------------------------------------------------------------
# Decision logic
# -----------------------------------------------------------------------------

def compute_buyback_propensity(
    member: dict,
    config: dict,
    rng: random.Random,
) -> float:
    """
    Compute probability this member will submit a buyback application.
    Probability is purely a function of demographics (no engagement signal yet,
    since portal events are generated separately in M5).
    """
    p = config["buyback"]["propensity"]
    base = p["base"]

    age = (date(2024, 1, 31) - member["DOB"]).days // 365
    if 45 <= age <= 60:
        base += p["age_45_60_bonus"]

    salary_band = member.get("SALARY_BAND_CODE")
    if salary_band in ("SR", "EX"):
        base += p["salary_sr_ex_bonus"]

    if member.get("SEX_CODE") == "2":
        base += p["female_bonus"]

    # NOTE: seminar attendance and portal usage bonuses are not applied here
    # because those event streams are generated independently in M5. In the
    # final dbt model, the propensity learned from data will reflect them
    # as features (the data will show correlation even if generator doesn't
    # explicitly set it here).

    return min(base, p["max_probability"])


def make_buyback_plan(
    member: dict,
    config: dict,
    rng: random.Random,
    history_start: date,
    history_end: date,
) -> Optional[MemberBuybackPlan]:
    """
    For a given eligible member, decide if they will buyback during the
    history window. Returns None if they don't apply.
    """
    eligible_service = member.get("ELIGIBLE_BUYBACK_SERVICE")
    if eligible_service is None or eligible_service <= 0:
        return None

    propensity = compute_buyback_propensity(member, config, rng)
    if not roll(propensity, rng):
        return None

    bb = config["buyback"]

    # Pick category
    category = _weighted_choice(bb["category_distribution"], rng)

    # Within window or open option
    is_within = roll(bb["within_window_rate"], rng)

    # Application date
    leave_end = member.get("LAST_BUYBACK_LEAVE_END_DATE")
    if leave_end is None:
        # Synthesize a leave end date — should not happen if eligible_service set,
        # but handle gracefully
        leave_end = history_start + timedelta(days=rng.randint(0, 365))

    if is_within:
        # 0-23 months after leave end
        max_app = leave_end + timedelta(days=23 * 30)
        min_app = leave_end + timedelta(days=30)
    else:
        # 25-60 months after leave end (open option)
        min_app = leave_end + timedelta(days=25 * 30)
        max_app = leave_end + timedelta(days=60 * 30)

    # Clamp to history window
    min_app = max(min_app, history_start)
    max_app = min(max_app, history_end)
    if min_app >= max_app:
        return None  # Can't fit in history

    application_date = random_date_between(min_app, max_app, rng)
    months_since = (application_date - leave_end).days // 30

    # Cost calculation
    salary = member.get("ANNUAL_SALARY") or 50000.0  # fallback for retired
    if salary < 1000:  # likely retired/terminated with $0 stored salary
        salary = 50000.0   # use median for cost calc

    if is_within:
        member_cost = round(eligible_service * salary * 0.03, 2)
        employer_cost = round(eligible_service * salary * 0.03, 2)
        total = member_cost + employer_cost
    else:
        base = eligible_service * salary * 0.06
        premium = rng.uniform(*bb["open_option_premium_range"])
        member_cost = round(base * (1 + premium), 2)
        employer_cost = 0.0
        total = member_cost

    # Payment method
    payment_method = _weighted_choice(bb["payment_method"], rng)
    if payment_method == "INSTALLMENT":
        opts = bb["installment_months_options"]["within_window" if is_within else "open_option"]
        installment_months = rng.choice(opts)
    else:
        installment_months = None

    # Chain outcome
    chain_outcome = _weighted_choice(bb["chain_outcomes"], rng)

    return MemberBuybackPlan(
        member_id=str(member["MEMBER_ID"]).zfill(10),
        employer_id=member["EMPLOYER_ID"],
        application_date=application_date,
        buyback_category=category,
        buyback_service_years=eligible_service,
        salary_at_leave=salary,
        leave_end_date=leave_end,
        months_since_eligibility=months_since,
        is_within_window=is_within,
        payment_method=payment_method,
        installment_months=installment_months,
        chain_outcome=chain_outcome,
        member_cost=member_cost,
        employer_cost=employer_cost,
        total_cost=total,
    )


def _weighted_choice(d: dict, rng: random.Random):
    keys = list(d.keys())
    weights = [d[k] for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


# -----------------------------------------------------------------------------
# Event row construction
# -----------------------------------------------------------------------------

def _common_buyback_fields(plan: MemberBuybackPlan) -> dict:
    """Fields that repeat across all events in a buyback chain."""
    return {
        "buyback_category_code": plan.buyback_category,
        "buyback_service_years": f"{plan.buyback_service_years:.2f}",
        "leave_end_date": plan.leave_end_date.isoformat(),
        "months_since_eligibility": plan.months_since_eligibility,
        "is_within_window": "Y" if plan.is_within_window else "N",
        "is_open_option": "N" if plan.is_within_window else "Y",
        "member_cost": f"{plan.member_cost:.2f}",
        "employer_cost": f"{plan.employer_cost:.2f}",
        "total_cost": f"{plan.total_cost:.2f}",
        "payment_method": plan.payment_method,
        "installment_months": plan.installment_months or "",
    }


def _make_event_row(
    plan: MemberBuybackPlan,
    event_type: str,
    event_dt: datetime,
    status: str,
    channel: str,
    rng: random.Random,
    messiness: dict,
    notes: str = "",
) -> dict:
    """Build a complete event row dict."""
    me = messiness["life_events"]
    event_id = generate_event_id(rng)

    # Apply timezone drift
    timestamp_str = format_timestamp_with_timezone_drift(
        event_dt, rng, me["timezone_mixed"],
    )

    # Apply notes garbage
    final_notes = maybe_garbage_notes(notes, rng, me["notes_garbage_text"]) if notes else ""

    row = {
        "event_id": event_id,
        "member_id": plan.member_id,
        "employer_id": plan.employer_id,
        "event_type_code": event_type,
        "event_date": event_dt.date().isoformat(),
        "event_timestamp": timestamp_str,
        "event_status": status,
        "channel_code": channel,
        "notes": final_notes,
    }
    row.update(_common_buyback_fields(plan))
    return row


def generate_buyback_chain(
    plan: MemberBuybackPlan,
    rng: random.Random,
    messiness: dict,
    history_end: date,
) -> list[dict]:
    """
    Generate the full event chain for one buyback. Returns list of event dicts
    in chronological order.

    Chain outcomes:
      normal:    APP → QUOTE → APPROVED → COMPLETE (or installments)
      rejected:  APP → QUOTE → APPROVED (status=REJECTED)
      cancelled: APP → CANCELLED
      abandoned: APP → QUOTE (then silence)
    """
    events = []
    me = messiness["life_events"]

    # APP
    app_dt = datetime.combine(
        plan.application_date,
        datetime.min.time().replace(
            hour=rng.randint(8, 17), minute=rng.randint(0, 59),
        ),
    )
    events.append(_make_event_row(
        plan, "BBK_APP", app_dt, "SUBMITTED", "PORTAL", rng, messiness,
    ))

    if plan.chain_outcome == "cancelled":
        # Cancelled within 7 days
        cancel_dt = app_dt + timedelta(days=rng.randint(1, 7))
        if cancel_dt.date() <= history_end:
            events.append(_make_event_row(
                plan, "BBK_CANCELLED", cancel_dt, "CANCELLED", "PORTAL", rng, messiness,
                notes="Member cancelled application",
            ))
        return events

    # QUOTE (+5 BD)
    quote_date = add_business_days(plan.application_date, 5)
    if quote_date > history_end:
        return events
    quote_dt = datetime.combine(
        quote_date,
        datetime.min.time().replace(hour=10, minute=rng.randint(0, 59)),
    )
    events.append(_make_event_row(
        plan, "BBK_QUOTE", quote_dt, "QUOTED", "SYSTEM", rng, messiness,
    ))

    # Abandoned: stop here (member never responds to quote)
    if plan.chain_outcome == "abandoned":
        return events

    # APPROVED (+14 BD from APP)
    approved_date = add_business_days(plan.application_date, 14)
    if approved_date > history_end:
        return events
    approved_dt = datetime.combine(
        approved_date,
        datetime.min.time().replace(hour=9, minute=rng.randint(0, 59)),
    )
    if plan.chain_outcome == "rejected":
        events.append(_make_event_row(
            plan, "BBK_APPROVED", approved_dt, "REJECTED", "SYSTEM", rng, messiness,
            notes="Insufficient documentation",
        ))
        return events

    events.append(_make_event_row(
        plan, "BBK_APPROVED", approved_dt, "APPROVED", "SYSTEM", rng, messiness,
    ))

    # COMPLETE (lump) or installments
    if plan.payment_method == "LUMP_SUM":
        complete_dt = approved_dt + timedelta(days=1)
        if complete_dt.date() <= history_end:
            events.append(_make_event_row(
                plan, "BBK_COMPLETE", complete_dt, "COMPLETED", "SYSTEM", rng, messiness,
            ))
        return events

    # Installments: generate monthly payments
    monthly_amount = plan.member_cost / plan.installment_months
    payment_date = approved_date + timedelta(days=30)
    for i in range(plan.installment_months):
        if payment_date > history_end:
            break
        pay_dt = datetime.combine(payment_date, datetime.min.time().replace(hour=2, minute=0))
        installment_plan = MemberBuybackPlan(
            **{**plan.__dict__, "member_cost": round(monthly_amount, 2),
               "total_cost": round(monthly_amount, 2), "employer_cost": 0.0}
        )
        events.append(_make_event_row(
            installment_plan, "BBK_INSTALLMENT_PAY", pay_dt,
            "COMPLETED", "SYSTEM", rng, messiness,
            notes=f"Installment {i+1} of {plan.installment_months}",
        ))
        payment_date += timedelta(days=30)
        # Final installment is also BBK_COMPLETE
        if i == plan.installment_months - 1:
            events.append(_make_event_row(
                plan, "BBK_COMPLETE", pay_dt + timedelta(seconds=1),
                "COMPLETED", "SYSTEM", rng, messiness,
                notes="Final installment processed",
            ))

    return events


# -----------------------------------------------------------------------------
# Non-buyback events (BENE_UPD, MARITAL, ADDR_CHG)
# -----------------------------------------------------------------------------

def generate_non_buyback_events(
    members: list[dict],
    history_start: date,
    history_end: date,
    rng: random.Random,
    messiness: dict,
) -> list[dict]:
    """
    Generate beneficiary updates, marital changes, address changes.
    Volume: ~40 BENE_UPD + ~15 MARITAL + ~100 ADDR_CHG per month.
    """
    events = []
    months = ((history_end.year - history_start.year) * 12 +
              history_end.month - history_start.month + 1)

    targets = [
        ("BENE_UPD", 40, "Beneficiary update"),
        ("MARITAL", 15, "Marital status change"),
        ("ADDR_CHG", 100, "Address change"),
    ]

    me = messiness["life_events"]

    for event_type, monthly_count, default_note in targets:
        total = monthly_count * months
        for _ in range(total):
            member = rng.choice(members)
            event_date = random_date_between(history_start, history_end, rng)
            event_dt = datetime.combine(
                event_date,
                datetime.min.time().replace(
                    hour=rng.randint(7, 22), minute=rng.randint(0, 59),
                ),
            )
            timestamp_str = format_timestamp_with_timezone_drift(
                event_dt, rng, me["timezone_mixed"],
            )
            row = {
                "event_id": generate_event_id(rng),
                "member_id": str(member["MEMBER_ID"]).zfill(10),
                "employer_id": member["EMPLOYER_ID"],
                "event_type_code": event_type,
                "event_date": event_date.isoformat(),
                "event_timestamp": timestamp_str,
                "event_status": "COMPLETED",
                "channel_code": rng.choice(["PORTAL", "MAIL", "PHONE", "ADVISOR"]),
                "notes": default_note if not roll(me["notes_garbage_text"], rng) else "",
                # Non-buyback events have null buyback fields:
                "buyback_category_code": "",
                "buyback_service_years": "",
                "leave_end_date": "",
                "months_since_eligibility": "",
                "is_within_window": "",
                "is_open_option": "",
                "member_cost": "",
                "employer_cost": "",
                "total_cost": "",
                "payment_method": "",
                "installment_months": "",
            }
            events.append(row)

    return events


# -----------------------------------------------------------------------------
# Bucketing events into monthly files
# -----------------------------------------------------------------------------

def bucket_events_by_month(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by YYYYMM key."""
    buckets = defaultdict(list)
    for ev in events:
        date_str = ev["event_date"]
        month_key = date_str[:7].replace("-", "")  # 2024-01-08 → 202401
        buckets[month_key].append(ev)
    return buckets


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------

def generate(
    config_path: Path,
    messiness_path: Path,
    layout_path: Path,
    member_dat_path: Path,
    output_dir: Path,
) -> dict:
    """Full M4 pipeline. Returns stats."""
    with config_path.open() as f:
        config = yaml.safe_load(f)
    with messiness_path.open() as f:
        messiness = yaml.safe_load(f)
    layout = FixedWidthLayout.from_yaml(layout_path)

    plan_code = config["plan"]["plan_code"]
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    history_months = config["history"]["life_events_months"]

    # History window: 24 months back from as_of (rough month math)
    history_end = as_of
    history_start_year = as_of.year
    history_start_month = as_of.month - history_months + 1
    while history_start_month <= 0:
        history_start_month += 12
        history_start_year -= 1
    history_start = date(history_start_year, history_start_month, 1)
    logger.info("History window: %s to %s", history_start, history_end)

    seed = config["seeds"]["life_event"]
    rng = random.Random(seed)

    # Load members
    logger.info("Loading members from: %s", member_dat_path)
    members = list(iter_member_census(member_dat_path, layout))
    logger.info("  Loaded %d members", len(members))

    # Filter to active+deferred (the only ones with buyback eligibility)
    eligible = [
        m for m in members
        if m["STATUS_CODE"] in ("A", "D") and m.get("ELIGIBLE_BUYBACK_SERVICE")
    ]
    logger.info("  Buyback-eligible members: %d", len(eligible))

    # Build buyback plans
    plans = []
    for member in eligible:
        plan = make_buyback_plan(member, config, rng, history_start, history_end)
        if plan is not None:
            plans.append(plan)
    logger.info("  Members who will submit buyback: %d", len(plans))

    # Generate buyback event chains
    buyback_events = []
    chain_outcome_counts = defaultdict(int)
    for plan in plans:
        chain_outcome_counts[plan.chain_outcome] += 1
        buyback_events.extend(generate_buyback_chain(plan, rng, messiness, history_end))
    logger.info("  Buyback event rows: %d", len(buyback_events))

    # Generate non-buyback events
    logger.info("Generating non-buyback events...")
    non_buyback_events = generate_non_buyback_events(
        members, history_start, history_end, rng, messiness,
    )
    logger.info("  Non-buyback event rows: %d", len(non_buyback_events))

    # Combine
    all_events = buyback_events + non_buyback_events
    logger.info("Total events: %d", len(all_events))

    # Bucket by month
    buckets = bucket_events_by_month(all_events)
    logger.info("Distinct months with events: %d", len(buckets))

    # Write monthly files
    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    for month_key, events in sorted(buckets.items()):
        # month_key like "202401"
        out_path = output_dir / f"{plan_code}_LIFE_EVENTS_{month_key}.TXT"
        # Sort within month by event_date then event_timestamp
        events.sort(key=lambda e: (e["event_date"], e["event_timestamp"]))
        with PipeDelimitedWriter(out_path) as w:
            w.write_column_header(OUTPUT_COLUMNS)
            for ev in events:
                w.write_row(ev, OUTPUT_COLUMNS)
        files_written += 1

    # Generate empty-month placeholders to ensure 24 files exist
    expected_months = []
    cur_year, cur_month = history_start.year, history_start.month
    while date(cur_year, cur_month, 1) <= history_end:
        key = f"{cur_year:04d}{cur_month:02d}"
        expected_months.append(key)
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    missing = [m for m in expected_months if m not in buckets]
    for month_key in missing:
        out_path = output_dir / f"{plan_code}_LIFE_EVENTS_{month_key}.TXT"
        with PipeDelimitedWriter(out_path) as w:
            w.write_column_header(OUTPUT_COLUMNS)
        files_written += 1

    return {
        "files_written": files_written,
        "buyback_event_count": len(buyback_events),
        "non_buyback_event_count": len(non_buyback_events),
        "plans_count": len(plans),
        "eligible_count": len(eligible),
        "chain_outcomes": dict(chain_outcome_counts),
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ONCAP life events.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = generate(
        config_path=args.config,
        messiness_path=args.messiness,
        layout_path=args.layout,
        member_dat_path=args.member_dat,
        output_dir=args.output_dir,
    )

    print()
    print("=" * 70)
    print("Life Events Generator — Summary")
    print("=" * 70)
    print(f"  Files written:           {stats['files_written']}")
    print(f"  Eligible members:        {stats['eligible_count']:,}")
    print(f"  Members who applied:     {stats['plans_count']:,}")
    print(f"  Buyback event rows:      {stats['buyback_event_count']:,}")
    print(f"  Non-buyback event rows:  {stats['non_buyback_event_count']:,}")
    print(f"\n  Chain outcomes:")
    for outcome, count in stats['chain_outcomes'].items():
        pct = count / stats['plans_count'] * 100 if stats['plans_count'] else 0
        print(f"    {outcome:<12}: {count:>5,} ({pct:5.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
