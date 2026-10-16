"""
Buyback Journey Simulator — Stage 2b (ground truth)

Single place that decides what each buyback-eligible member *actually did*:
experiment assignment, campaign email outcomes, portal visits, and buyback
applications. Downstream "renderer" generators (email, portal, life events)
read this ground truth and emit their own system-specific files with their
own messiness. This keeps every source linked by construction.

Outputs:
  data/synthetic/_ground_truth/journey_members.csv   one row per eligible member
  data/synthetic/_ground_truth/journey_touches.csv   one row per email/portal touch
      -> NOT a pipeline source. Used by renderers and to verify that the
         analysis recovers the designed campaign effect.
  data/synthetic/campaign_assignment/
      ONCAP001_CAMPAIGN_ASSIGNMENT_v1_<date>.csv        CRM export (clean-ish)
      ONCAP001_CAMPAIGN_ASSIGNMENT_v2_FINAL_<date>.csv  Excel re-export (messy)

Model (daily, America/Toronto local dates):
  hazard_day = h_base x window_factor x campaign_factor
    h_base         from buyback.propensity (24-month probability), per member
    window_factor  1.0 inside 24-month window, x surge in last N months,
                   x open_option_multiplier for months 24-59, 0 afterwards
    campaign_factor campaign_multiplier[stratum] for campaign_effect_days
                   after a *delivered* campaign email (causal path)
  Open/click propensity scales with relative h_base, so clickers are
  self-selected high-intent members (naive click analysis overstates lift).

Usage:
  python -m upstream_simulators.generators.journey_simulator
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml


logger = logging.getLogger("journey_simulator")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "upstream_simulators" / "config" / "plan_config.yaml"
DEFAULT_MESSINESS = PROJECT_ROOT / "upstream_simulators" / "config" / "messiness_config.yaml"
DEFAULT_LAYOUT = PROJECT_ROOT / "upstream_simulators" / "config" / "record_layouts" / "member_census_layout.yaml"
DEFAULT_MEMBER_DAT = PROJECT_ROOT / "data" / "synthetic" / "member_census" / "ONCAP001_MEMBER_CENSUS_20240131.DAT"
DEFAULT_GT_DIR = PROJECT_ROOT / "data" / "synthetic" / "_ground_truth"
DEFAULT_ASSIGN_DIR = PROJECT_ROOT / "data" / "synthetic" / "campaign_assignment"

PORTAL_HISTORY_MONTHS_FALLBACK = 12


# -----------------------------------------------------------------------------
# Small date helpers (kept local so this module has no hidden coupling)
# -----------------------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    # clamp day (e.g. Jan 31 + 1 month -> Feb 28/29)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def months_between(start: date, d: date) -> int:
    """Whole months elapsed from start to d (floor)."""
    m = (d.year - start.year) * 12 + (d.month - start.month)
    if d.day < start.day:
        m -= 1
    return m


def at_time(d: date, rng: random.Random, h_lo: int, h_hi: int) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(
        hour=rng.randint(h_lo, h_hi), minute=rng.randint(0, 59), second=rng.randint(0, 59)
    )


def stable_frac(key: str) -> float:
    """Deterministic [0,1) from a string (member-level traits, no RNG use)."""
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) / 0x100000000


# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass
class Member:
    member_id: str
    employer_id: str
    dob: date
    sex_code: str
    salary_band: str
    annual_salary: float
    buyback_years: float
    email: Optional[str]
    census_start: Optional[date]          # as shown in census (may be defective)
    true_start: date                      # what really happened
    start_defect: str                     # "", "missing", "future"
    p24: float = 0.0
    rel: float = 1.0
    is_mpp: bool = False
    # experiment
    in_v1: bool = False
    in_v2: bool = False
    stratum: str = ""                     # within_window / open_option / guardrail
    arm: str = ""                         # treatment / control / guardrail
    contaminated: bool = False
    exclusion_reason: str = ""
    # campaign outcomes
    sends: list = field(default_factory=list)   # list of (send_date, delivered)
    unsubscribed_on: Optional[date] = None
    hard_bounced_on: Optional[date] = None
    # application
    applied_on: Optional[date] = None
    app: dict = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Member loading / scoring
# -----------------------------------------------------------------------------

def age_on(dob: date, d: date) -> int:
    return d.year - dob.year - ((d.month, d.day) < (dob.month, dob.day))


def p24_for(m: Member, config: dict, as_of: date) -> float:
    """Same demographic propensity as the original life_event generator."""
    p = config["buyback"]["propensity"]
    base = p["base"]
    if 45 <= age_on(m.dob, as_of) <= 60:
        base += p["age_45_60_bonus"]
    if m.salary_band in ("SR", "EX"):
        base += p["salary_sr_ex_bonus"]
    if m.sex_code == "2":
        base += p["female_bonus"]
    return min(base, p["max_probability"])


def build_members(census_rows, config, messiness, rng) -> list[Member]:
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    out = []
    for r in census_rows:
        if r["STATUS_CODE"] != "A" or not r.get("ELIGIBLE_BUYBACK_SERVICE"):
            continue
        census_start = r.get("LAST_BUYBACK_LEAVE_END_DATE")
        defect = ""
        if census_start is None:
            defect = "missing"
        elif census_start > as_of:
            defect = "future"
        # Defective rows still had a real start date; draw one for simulation.
        true_start = census_start if not defect else (
            as_of - timedelta(days=rng.randint(30, 365 * 5))
        )
        mid = str(r["MEMBER_ID"]).zfill(10)
        email = r.get("EMAIL") or None
        out.append(Member(
            member_id=mid,
            employer_id=r["EMPLOYER_ID"],
            dob=r["DOB"],
            sex_code=r.get("SEX_CODE", ""),
            salary_band=r.get("SALARY_BAND_CODE", ""),
            annual_salary=float(r.get("ANNUAL_SALARY") or 0.0),
            buyback_years=float(r["ELIGIBLE_BUYBACK_SERVICE"]),
            email=email,
            census_start=census_start,
            true_start=true_start,
            start_defect=defect,
        ))
    share = messiness["email_engagement"]["apple_mpp_member_share"]
    for m in out:
        m.p24 = p24_for(m, config, as_of)
        # Mail-client trait is a property of the person, not of each email.
        m.is_mpp = m.email is not None and stable_frac("mpp:" + m.member_id) < share
    mean_p = sum(m.p24 for m in out) / max(len(out), 1)
    for m in out:
        m.rel = m.p24 / mean_p if mean_p else 1.0
    return out


# -----------------------------------------------------------------------------
# Hazard model
# -----------------------------------------------------------------------------

def window_factor(m: Member, d: date, cfg_j: dict, cfg_e: dict) -> float:
    if d < m.true_start:
        return 0.0
    k = months_between(m.true_start, d)
    win = cfg_e["window_months"]
    if k < win:
        if k >= win - cfg_j["deadline_surge_months"]:
            return cfg_j["deadline_surge_multiplier"]
        return 1.0
    if k < cfg_e["open_option_max_months"]:
        return cfg_j["open_option_multiplier"]
    return 0.0


def daily_base(m: Member) -> float:
    # 24-month probability -> daily hazard
    return 1 - (1 - m.p24) ** (1 / (24 * 30.44))


def campaign_factor(m: Member, d: date, cfg_c: dict, cfg_j: dict) -> float:
    eff_days = cfg_j["campaign_effect_days"]
    for send_date, delivered in m.sends:
        if delivered and send_date <= d < send_date + timedelta(days=eff_days):
            in_window = d < add_months(m.true_start, 24)
            key = "within_window" if in_window else "open_option"
            return cfg_j["campaign_multiplier"][key]
    return 1.0


def simulate_days(m: Member, start: date, end: date, rng, cfg_c, cfg_j, cfg_e) -> None:
    """Advance one member day by day; stop at first application."""
    if m.applied_on is not None:
        return
    base = daily_base(m)
    d = start
    while d < end:
        wf = window_factor(m, d, cfg_j, cfg_e)
        if wf > 0:
            h = base * wf * campaign_factor(m, d, cfg_c, cfg_j)
            if rng.random() < h:
                m.applied_on = d
                return
        d += timedelta(days=1)


# -----------------------------------------------------------------------------
# Experiment assignment
# -----------------------------------------------------------------------------

def assign_experiment(members, config, messiness, rng) -> dict:
    c = config["campaign"]
    ca = messiness["campaign_assignment"]
    assigned = date.fromisoformat(c["assignment_date"])
    launch = date.fromisoformat(c["treatment_send_date"])
    v2_date = date.fromisoformat(ca["v2_refresh_date"])
    crm_lag = ca.get("crm_sync_lag_days", 30)
    guard = c["deadline_guardrail_months"]
    win = config["eligibility"]["window_months"]
    oo_max = config["eligibility"]["open_option_max_months"]

    pools = defaultdict(list)
    for m in members:
        if m.start_defect:
            m.exclusion_reason = f"start_{m.start_defect}"
            continue
        if m.true_start > assigned:
            m.exclusion_reason = "not_yet_eligible"
            continue
        if launch >= add_months(m.true_start, oo_max):
            m.exclusion_reason = "beyond_open_option"
            continue
        # CRM lags the admin system: recent appliers still look eligible.
        if m.applied_on is not None and m.applied_on < assigned - timedelta(days=crm_lag):
            m.exclusion_reason = "applied_before_list"
            continue
        m.in_v1 = True
        window_end = add_months(m.true_start, win)
        if launch < window_end <= add_months(launch, guard):
            m.stratum, m.arm = "guardrail", "guardrail"
            continue
        m.stratum = "within_window" if launch < window_end else "open_option"
        pools[m.stratum].append(m)

    # Stratified, exactly balanced randomization
    share = c["treatment_share"]
    for stratum, pool in pools.items():
        pool.sort(key=lambda x: x.member_id)
        rng.shuffle(pool)
        n_t = round(len(pool) * share)
        for i, m in enumerate(pool):
            m.arm = "treatment" if i < n_t else "control"

    # v2 re-export drops anyone the CRM now shows as applied
    for m in members:
        if m.in_v1:
            m.in_v2 = not (m.applied_on is not None and m.applied_on < v2_date)

    # Execution error: a few control members land on the first send list
    for m in members:
        if m.in_v2 and m.arm == "control" and rng.random() < ca["control_contamination"]:
            m.contaminated = True

    return {s: len(p) for s, p in pools.items()}


# -----------------------------------------------------------------------------
# Campaign email outcomes (ground truth touches)
# -----------------------------------------------------------------------------

def send_campaign(m: Member, send_date: date, config, messiness, rng, touches) -> None:
    c = config["campaign"]
    j = config["journey"]
    me = messiness["email_engagement"]
    if m.email is None:
        return                                   # non-compliance: cannot be reached
    if m.unsubscribed_on and m.unsubscribed_on <= send_date:
        return
    sent = at_time(send_date, rng, 9, 14)

    def t(kind, ts, source="human", extra=""):
        touches.append({"member_id": m.member_id, "channel": "email",
                        "touch_type": kind, "ts_local": ts.isoformat(timespec="seconds"),
                        "campaign_id": c["campaign_id"], "source": source, "detail": extra})

    t("SENT", sent, "system")
    if rng.random() < me["bounce_rate"]:
        hard = rng.random() < me["hard_bounce_share"]
        t("BOUNCED", sent + timedelta(minutes=2), "system", "hard" if hard else "soft")
        if hard:
            m.hard_bounced_on = send_date
        m.sends.append((send_date, False))
        return
    delivered = sent + timedelta(minutes=1)
    t("DELIVERED", delivered, "system")
    m.sends.append((send_date, True))

    if m.is_mpp:                                   # Apple MPP prefetch
        t("OPENED", delivered + timedelta(seconds=rng.randint(1, 60)), "machine_mpp")
    if rng.random() < me["security_scanner_click_rate"]:
        t("CLICKED", delivered + timedelta(seconds=rng.randint(1, 30)), "machine_scanner",
          c["landing_url"])

    p_open = min(j["human_open_rate"] * m.rel, 0.9)
    if rng.random() < p_open:
        opened = delivered + timedelta(minutes=rng.randint(5, 3 * 24 * 60))
        p_click = min(j["click_given_open"] * m.rel, 0.8)
        clicked = rng.random() < p_click
        pixel_blocked = clicked and rng.random() < j["click_without_open_share"]
        if not pixel_blocked:
            t("OPENED", opened, "human")
        if clicked:
            click_ts = opened + timedelta(seconds=rng.randint(5, 600))
            t("CLICKED", click_ts, "human", c["landing_url"])
            pages = "buyback_info"
            if rng.random() < min(0.3 * m.rel, 0.9):
                pages += ">portal_login>buyback_quote"
            touches.append({"member_id": m.member_id, "channel": "portal",
                            "touch_type": "SESSION", "source": "email_click",
                            "ts_local": (click_ts + timedelta(seconds=rng.randint(2, 20))).isoformat(timespec="seconds"),
                            "campaign_id": c["campaign_id"], "detail": pages})
    if rng.random() < me["unsubscribe_rate"]:
        m.unsubscribed_on = send_date
        t("UNSUBSCRIBED", sent + timedelta(hours=rng.randint(1, 48)), "human")


# -----------------------------------------------------------------------------
# Application details
# -----------------------------------------------------------------------------

def _wchoice(d: dict, rng):
    keys = list(d)
    return rng.choices(keys, weights=[d[k] for k in keys], k=1)[0]


def build_application(m: Member, config, messiness, rng, touches) -> None:
    bb = config["buyback"]
    j = config["journey"]
    le = messiness["life_events"]
    d = m.applied_on
    window_end = add_months(m.true_start, config["eligibility"]["window_months"])
    is_within = d < window_end
    salary = m.annual_salary if m.annual_salary >= 1000 else 50000.0
    if is_within:
        member_cost = round(m.buyback_years * salary * 0.03, 2)
        employer_cost = member_cost
    else:
        premium = rng.uniform(*bb["open_option_premium_range"])
        member_cost = round(m.buyback_years * salary * 0.06 * (1 + premium), 2)
        employer_cost = 0.0
    payment = _wchoice(bb["payment_method"], rng)
    installments = None
    if payment == "INSTALLMENT":
        installments = rng.choice(bb["installment_months_options"]["within_window" if is_within else "open_option"])

    age = age_on(m.dob, d)
    p_paper = j["paper_application_rate"]["age_60_plus" if age >= 60 else "under_60"]
    channel = "MAIL" if rng.random() < p_paper else "PORTAL"
    entered = d
    if channel == "MAIL":
        entered = d + timedelta(days=rng.randint(*le["paper_entry_lag_days"]))
    else:
        # Portal applicants research first: a session in the 0-14 days before.
        start = at_time(d - timedelta(days=rng.randint(0, 14)), rng, 7, 21)
        touches.append({"member_id": m.member_id, "channel": "portal", "touch_type": "SESSION",
                        "source": "pre_application", "ts_local": start.isoformat(timespec="seconds"),
                        "campaign_id": "", "detail": "portal_login>buyback_info>buyback_quote"})

    outcome = _wchoice(bb["chain_outcomes"], rng)
    reapply_on = None
    if rng.random() < le["reapply_rate"]:
        outcome = "cancelled"
        reapply_on = d + timedelta(days=rng.randint(10, 40))

    m.app = {
        "application_date": d.isoformat(),
        "entered_date": entered.isoformat(),
        "channel": channel,
        "is_within_window": "Y" if is_within else "N",
        "months_since_eligibility": months_between(m.true_start, d),
        "buyback_category": _wchoice(bb["category_distribution"], rng),
        "payment_method": payment,
        "installment_months": installments or "",
        "chain_outcome": outcome,
        "member_cost": f"{member_cost:.2f}",
        "employer_cost": f"{employer_cost:.2f}",
        "total_cost": f"{member_cost + employer_cost:.2f}",
        "reapply_date": reapply_on.isoformat() if reapply_on else "",
    }


# -----------------------------------------------------------------------------
# Organic portal behaviour (non-campaign)
# -----------------------------------------------------------------------------

def organic_visits(m: Member, p_start: date, p_end: date, config, rng, touches) -> None:
    monthly = config["journey"]["organic_info_view_monthly"] * m.rel
    daily = 1 - (1 - min(monthly, 0.9)) ** (1 / 30.44)
    d = max(p_start, m.true_start)
    stop = min(p_end, m.applied_on or p_end)
    while d < stop:
        if rng.random() < daily:
            touches.append({"member_id": m.member_id, "channel": "portal", "touch_type": "SESSION",
                            "source": "organic", "ts_local": at_time(d, rng, 7, 22).isoformat(timespec="seconds"),
                            "campaign_id": "", "detail": "portal_login>buyback_info"})
        d += timedelta(days=1)


# -----------------------------------------------------------------------------
# Assignment export files (marketing's CRM export, then an Excel re-save)
# -----------------------------------------------------------------------------

ARM_LABELS = {
    "treatment": ["Treatment", "treatment", "TRT"],
    "control": ["Control", "control", "Holdout"],
    "guardrail": ["Guardrail - Always Send", "guardrail"],
}


def _label(arm: str, rng, rate: float) -> str:
    canonical = {"treatment": "Treatment", "control": "Control", "guardrail": "Guardrail - Always Send"}[arm]
    return rng.choice(ARM_LABELS[arm][1:]) if rng.random() < rate else canonical


def write_assignment_files(members, config, messiness, out_dir: Path, rng) -> tuple[Path, Path]:
    c = config["campaign"]
    ca = messiness["campaign_assignment"]
    plan = config["plan"]["plan_code"]
    out_dir.mkdir(parents=True, exist_ok=True)
    v1_rows = sorted((m for m in members if m.in_v1), key=lambda m: m.member_id)
    rate = ca["arm_label_variant_rate"]
    launch = date.fromisoformat(c["treatment_send_date"])
    delayed = date.fromisoformat(c["control_send_date"])

    def send_date(m):
        return delayed if m.arm == "control" else launch

    v1 = out_dir / f"{plan}_CAMPAIGN_ASSIGNMENT_v1_{c['assignment_date'].replace('-', '')}.csv"
    with v1.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["member_id", "campaign_id", "segment", "arm", "assigned_date", "scheduled_send_date"])
        for m in v1_rows:
            w.writerow([m.member_id, c["campaign_id"], m.stratum, _label(m.arm, rng, rate),
                        c["assignment_date"], send_date(m).isoformat()])

    # v2: re-exported after the CRM caught up, opened & saved in Excel.
    v2_rows = [m for m in v1_rows if m.in_v2]
    v2 = out_dir / f"{plan}_CAMPAIGN_ASSIGNMENT_v2_FINAL_{ca['v2_refresh_date'].replace('-', '')}.csv"

    def us(d: date) -> str:                       # Excel US locale: M/D/YYYY
        return f"{d.month}/{d.day}/{d.year}"

    with v2.open("w", newline="", encoding="utf-8-sig") as f:   # Excel adds a BOM
        w = csv.writer(f)
        w.writerow(["Member ID", "Group", "Segment", "Send Date", "Campaign", "Assigned Date"])
        for m in v2_rows:
            mid = str(int(m.member_id)) if ca["v2_saved_in_excel"] else m.member_id
            w.writerow([mid, _label(m.arm, rng, rate), m.stratum, us(send_date(m)),
                        c["campaign_id"], us(date.fromisoformat(c["assignment_date"]))])
        if ca["total_row"]:
            w.writerow([f"Total: {len(v2_rows):,}", "", "", "", "", ""])
    return v1, v2


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------

def simulate(census_rows, config, messiness) -> tuple[list[Member], list[dict], dict]:
    rng = random.Random(config["seeds"]["journey"])
    c, j, e = config["campaign"], config["journey"], config["eligibility"]
    as_of = date.fromisoformat(config["plan"]["as_of_date"])
    le_months = config["history"]["life_events_months"]
    hist_start = add_months(as_of.replace(day=1), -(le_months - 1))
    hist_end = as_of + timedelta(days=1)
    assigned = date.fromisoformat(c["assignment_date"])
    launch = date.fromisoformat(c["treatment_send_date"])
    delayed = date.fromisoformat(c["control_send_date"])
    p_months = config["history"].get("portal_events_months", PORTAL_HISTORY_MONTHS_FALLBACK)
    portal_start = add_months(as_of.replace(day=1), -(p_months - 1))

    members = build_members(census_rows, config, messiness, rng)
    members.sort(key=lambda m: m.member_id)
    logger.info("Eligible active members: %d", len(members))

    # Phase 1: history start -> list pull
    for m in members:
        simulate_days(m, hist_start, assigned, rng, c, j, e)
    strata = assign_experiment(members, config, messiness, rng)
    logger.info("Randomized pools: %s", strata)

    touches: list[dict] = []
    # Phase 2: list pull -> launch (no campaign yet)
    for m in members:
        simulate_days(m, assigned, launch, rng, c, j, e)
    # Launch: treatment + guardrail + contaminated control, if not yet applied
    for m in members:
        if m.in_v2 and m.applied_on is None and (m.arm in ("treatment", "guardrail") or m.contaminated):
            send_campaign(m, launch, config, messiness, rng, touches)
    # Phase 3: launch -> delayed control send
    for m in members:
        simulate_days(m, launch, delayed, rng, c, j, e)
    for m in members:
        if m.in_v2 and m.arm == "control" and m.applied_on is None:
            send_campaign(m, delayed, config, messiness, rng, touches)
    # Phase 4: delayed send -> end of history
    for m in members:
        simulate_days(m, delayed, hist_end, rng, c, j, e)

    for m in members:
        if m.applied_on is not None:
            build_application(m, config, messiness, rng, touches)
        organic_visits(m, portal_start, hist_end, config, rng, touches)

    touches.sort(key=lambda t: (t["ts_local"], t["member_id"]))
    return members, touches, strata


def true_effect_summary(members, config) -> list[tuple]:
    """Ground-truth ITT: 90-day application rate by stratum x arm (v2 list, not applied before launch)."""
    c = config["campaign"]
    launch = date.fromisoformat(c["treatment_send_date"])
    horizon = launch + timedelta(days=c["observation_days"])
    agg = defaultdict(lambda: [0, 0])
    for m in members:
        if not m.in_v2 or m.arm not in ("treatment", "control"):
            continue
        if m.applied_on is not None and m.applied_on < launch:
            continue
        a = agg[(m.stratum, m.arm)]
        a[0] += 1
        a[1] += int(m.applied_on is not None and m.applied_on < horizon)
    return sorted((k[0], k[1], n, conv, conv / n if n else 0.0) for k, (n, conv) in agg.items())


MEMBER_COLS = [
    "member_id", "employer_id", "p24", "rel", "is_mpp", "has_email",
    "census_start", "true_start", "start_defect", "exclusion_reason",
    "in_v1", "in_v2", "stratum", "arm", "contaminated",
    "first_send_date", "delivered_first", "unsubscribed_on", "hard_bounced_on",
    "applied_on", "entered_date", "channel", "is_within_window", "months_since_eligibility",
    "buyback_category", "payment_method", "installment_months", "chain_outcome",
    "member_cost", "employer_cost", "total_cost", "reapply_date",
]
TOUCH_COLS = ["member_id", "channel", "touch_type", "ts_local", "campaign_id", "source", "detail"]


def write_ground_truth(members, touches, gt_dir: Path) -> None:
    gt_dir.mkdir(parents=True, exist_ok=True)
    with (gt_dir / "journey_members.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MEMBER_COLS)
        w.writeheader()
        for m in members:
            first = m.sends[0] if m.sends else (None, None)
            row = {
                "member_id": m.member_id, "employer_id": m.employer_id,
                "p24": f"{m.p24:.4f}", "rel": f"{m.rel:.4f}",
                "is_mpp": int(m.is_mpp), "has_email": int(m.email is not None),
                "census_start": m.census_start.isoformat() if m.census_start else "",
                "true_start": m.true_start.isoformat(), "start_defect": m.start_defect,
                "exclusion_reason": m.exclusion_reason,
                "in_v1": int(m.in_v1), "in_v2": int(m.in_v2), "stratum": m.stratum, "arm": m.arm,
                "contaminated": int(m.contaminated),
                "first_send_date": first[0].isoformat() if first[0] else "",
                "delivered_first": "" if first[1] is None else int(first[1]),
                "unsubscribed_on": m.unsubscribed_on.isoformat() if m.unsubscribed_on else "",
                "hard_bounced_on": m.hard_bounced_on.isoformat() if m.hard_bounced_on else "",
                "applied_on": m.applied_on.isoformat() if m.applied_on else "",
            }
            a = m.app
            row.update({
                "entered_date": a.get("entered_date", ""), "channel": a.get("channel", ""),
                "is_within_window": a.get("is_within_window", ""),
                "months_since_eligibility": a.get("months_since_eligibility", ""),
                "buyback_category": a.get("buyback_category", ""),
                "payment_method": a.get("payment_method", ""),
                "installment_months": a.get("installment_months", ""),
                "chain_outcome": a.get("chain_outcome", ""),
                "member_cost": a.get("member_cost", ""), "employer_cost": a.get("employer_cost", ""),
                "total_cost": a.get("total_cost", ""), "reapply_date": a.get("reapply_date", ""),
            })
            w.writerow(row)
    with (gt_dir / "journey_touches.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TOUCH_COLS)
        w.writeheader()
        w.writerows(touches)


def print_summary(members, touches, strata, effect) -> None:
    print("\n=== Buyback Journey Simulator ===")
    print(f"  Eligible active members:  {len(members):,}")
    print(f"  Exclusions:               {dict(Counter(m.exclusion_reason for m in members if m.exclusion_reason))}")
    print(f"  v1 list / v2 list:        {sum(m.in_v1 for m in members):,} / {sum(m.in_v2 for m in members):,}")
    print(f"  Arms (v2):                {dict(Counter((m.stratum, m.arm) for m in members if m.in_v2))}")
    print(f"  Control contaminated:     {sum(m.contaminated for m in members)}")
    print(f"  Applications (24 mo):     {sum(m.applied_on is not None for m in members):,}")
    print(f"  Touches by source:        {dict(Counter((t['channel'], t['source']) for t in touches))}")
    print("\n  TRUE 90-day ITT application rate (ground truth):")
    for stratum, arm, n, conv, rate in effect:
        print(f"    {stratum:<14} {arm:<10} n={n:>5,}  applied={conv:>4}  rate={rate:6.2%}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate buyback member journeys (ground truth).")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--messiness", type=Path, default=DEFAULT_MESSINESS)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--member-dat", type=Path, default=DEFAULT_MEMBER_DAT)
    ap.add_argument("--gt-dir", type=Path, default=DEFAULT_GT_DIR)
    ap.add_argument("--assign-dir", type=Path, default=DEFAULT_ASSIGN_DIR)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout
    from upstream_simulators.shared.writers.fixed_width_reader import iter_member_census

    config = yaml.safe_load(args.config.read_text())
    messiness = yaml.safe_load(args.messiness.read_text())
    layout = FixedWidthLayout.from_yaml(args.layout)
    rows = list(iter_member_census(args.member_dat, layout))

    members, touches, strata = simulate(rows, config, messiness)
    write_ground_truth(members, touches, args.gt_dir)
    dirt_rng = random.Random(config["seeds"]["campaign_dirt"])
    v1, v2 = write_assignment_files(members, config, messiness, args.assign_dir, dirt_rng)
    print_summary(members, touches, strata, true_effect_summary(members, config))
    print(f"\n  Wrote: {args.gt_dir}/journey_members.csv, journey_touches.csv")
    print(f"         {v1.name}, {v2.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
