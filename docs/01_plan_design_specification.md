# ONCAP Pension Plan — Plan Design Specification

**Document version**: 1.0
**Effective date**: 2024-01-31 (data as-of date)
**Prepared for**: Pension Data Pipeline Project (Week 1)
**Status**: Synthetic / Simulated — Not a real pension plan

> This document models the plan design of a fictional Ontario non-profit sector
> pension plan, inspired by OPTrust's main plan (OPSEU Pension Plan) and
> OPTrust Select. It serves as the authoritative business specification for
> synthetic data generation and downstream pipeline development.

---

## 1. Plan Overview

**Plan name**: ONCAP Pension Plan (Ontario Non-profit, Charitable and Public Sector Pension)

**Plan code**: `ONCAP001`

**Plan type**: Defined Benefit (DB), Jointly Sponsored Pension Plan (JSPP)

**Sponsor**: ONCAP Pension Trust (synthetic entity)

**Regulatory registration**:

- Pension Benefits Act of Ontario (registered with FSRA)
- Income Tax Act (Canada) — registered pension plan (RPP)

**Design basis**: Modeled after OPTrust's main plan (OPSEU Pension Plan) with
references to OPTrust Select for employer eligibility and non-profit focus.

**Plan effective date**: January 1, 2014

**Plan age as of snapshot**: 10 years

---

## 2. Eligibility

**Participating employers**: Charitable or non-profit organizations registered in
Ontario. Employer must sign a participation agreement with ONCAP.

**Member eligibility**:

- Full-time permanent employees: mandatory enrollment
- Part-time permanent (working ≥ 700 hours/year): eligible, optional
- Contract / temporary employees: not eligible

---

## 3. Contribution Structure

| Party    | Contribution Rate | Base                  |
|----------|-------------------|-----------------------|
| Member   | 3.0%              | Pensionable earnings  |
| Employer | 3.0% (match)      | Pensionable earnings  |

**Contribution frequency**: Follows each participating employer's payroll
cycle. Employers transmit contributions to ONCAP each pay cycle.

**Observed pay cycle distribution across ONCAP employers**:

| Pay Frequency | Code | % Employers | Pay Periods / Year |
|---------------|------|-------------|--------------------|
| Biweekly      | BW   | 60%         | 26                 |
| Semi-monthly  | SM   | 25%         | 24                 |
| Monthly       | MO   | 10%         | 12                 |
| Weekly        | WK   | 5%          | 52                 |

**Pensionable earnings**: Regular base salary + eligible overtime (excludes
bonuses, expense reimbursement).

---

## 4. Benefit Formula

**Annual pension at normal retirement**:

```
Annual Pension = Career Average Pensionable Earnings × 0.6% × Years of Credited Service
```

**Normal retirement age**: 65

**Accrual rate**: 0.6% per year of credited service

**Maximum service for pension calculation**: None (no service cap for accrual)

**Inflation protection**: Conditional (subject to annual Board approval based
on plan funded status)

---

## 5. Service Buyback Provisions

**What is a buyback**: A member's option to purchase credited pensionable
service for periods that were not originally credited to the plan.

### Eligible buyback categories

| Category                 | Code  | Description                                                 |
|--------------------------|-------|-------------------------------------------------------------|
| Maternity/Parental Leave | ML    | Unpaid portion of maternity or parental leave               |
| Leave of Absence         | LOA   | Medical, personal, educational unpaid leave                 |
| Prior Service Transfer   | PST   | Service earned in a previous Canadian registered pension plan |
| Pre-Enrollment Period    | PEP   | Waiting period before plan enrollment became effective      |
| Part-Time Top-Up         | PTT   | Contribution on regular hours during approved PT arrangement |

### Buyback cost sharing — depends on application timing

**Within 24-month application window** (regular buyback):

- Member pays 3% contribution equivalent
- Employer pays 3% match equivalent
- Total cost is **shared** between member and employer

**Outside 24-month window** (open option buyback):

- Member pays **100%** of cost (both member and employer shares)
- Cost is actuarially calculated and **significantly higher** than within-window
  cost (approximately 40–60% premium)
- Employer contributes nothing

### Application deadline definition

- For leaves (ML, LOA, PTT): 24 months from end of leave / PT arrangement
- For prior service (PST, PEP): 24 months from date of plan enrollment

### Payment options

- Lump sum (single payment)
- Installment plan:
  - Up to 10 years 3 months for within-window buybacks
  - Up to 60 months for open option buybacks

### Business KPI targets (for simulation)

| Metric                                              | Target          |
|-----------------------------------------------------|-----------------|
| Overall buyback conversion rate among eligible      | ~10%            |
| % of buybacks applied within 24-month window        | ~70%            |
| % open option                                       | ~30%            |
| Open option cost premium over within-window         | ~40–60% higher  |

---

## 6. Member Status Definitions

| Status                 | Code | Description                                           | Contributing? |
|------------------------|------|-------------------------------------------------------|---------------|
| Active                 | A    | Currently employed, accruing service                  | Yes           |
| Deferred Vested        | D    | Terminated employment, pension deferred to retirement | No            |
| Retired                | R    | Receiving pension payments                            | No            |
| Terminated Non-Vested  | T    | Terminated before vesting, benefits returned          | No            |
| Survivor / Beneficiary | S    | Receiving survivor pension                            | No            |

**Vesting**: 24 months of continuous service (after 24 months, member is
entitled to deferred pension upon termination).

---

## 7. Engagement Channels (Modeled)

The plan engages members through multiple channels, each generating data in the
event logs:

| Channel              | System                  | Engagement Type                              |
|----------------------|-------------------------|----------------------------------------------|
| Member Portal        | ONCAP Online Services   | Login, statement view, calculator use        |
| Call Center          | ONCAP Member Services   | Phone inquiries                              |
| Retirement Seminars  | Event platform          | Annual regional seminars                     |
| Email Communications | Email campaign platform | Newsletters, targeted campaigns              |
| Advisor Meetings     | Scheduling system       | 1-on-1 consultations (by request)            |

---

## 8. Plan Population (As of 2024-01-31)

**Total members**: 50,000

### Member status breakdown

| Status                | %    | Count  |
|-----------------------|------|--------|
| Active                | 55%  | 27,500 |
| Deferred Vested       | 20%  | 10,000 |
| Retired               | 15%  | 7,500  |
| Terminated Non-Vested | 8%   | 4,000  |
| Survivor              | 2%   | 1,000  |

**Participating employers**: 400 non-profit organizations across Ontario

**Geographic concentration**: All Ontario; Toronto metro ~50%, remaining
distributed across Ottawa, Hamilton, London, and smaller communities

### Demographic profile

- **Sex**: ~70% Female, ~28% Male, ~2% Unknown (reflects non-profit sector
  composition)
- **Active member age range**: 22–65, median ~42
- **Retired member age range**: 55–95, median ~71

### Salary distribution (active members)

| Salary Band | Code | Range                 | % of Active |
|-------------|------|-----------------------|-------------|
| Entry       | EN   | \$35,000 – \$50,000   | 30%         |
| Mid         | MD   | \$50,000 – \$75,000   | 45%         |
| Senior      | SR   | \$75,000 – \$110,000  | 20%         |
| Executive   | EX   | \$110,000 – \$180,000 | 5%          |

### Years of credited service (active members)

| Range        | %   |
|--------------|-----|
| 0–2 years    | 25% |
| 2–5 years    | 30% |
| 5–10 years   | 35% |
| 10+ years    | 10% |

---

## 9. Key Business Metrics (Target for Simulation)

| Metric                                              | Target Value (Annual) |
|-----------------------------------------------------|-----------------------|
| Total active contributions                          | ~\$75M                |
| Total pension payments                              | ~\$40M                |
| New buyback elections                               | ~800 events           |
| Buyback conversion rate (eligible → elected)        | ~10%                  |
| Buyback applications within 24-month window         | ~70%                  |
| Open option buybacks                                | ~30%                  |
| Portal monthly active users                         | ~40% of active        |
| Call center contact rate                            | ~60 calls / 100 active members |
| Seminar attendance                                  | ~15% of members aged 50+ |

---

## 10. Data Systems Landscape

Source systems modeled for synthetic data generation:

| System                  | Data Domain                          | Extract Format        | Frequency           |
|-------------------------|--------------------------------------|-----------------------|---------------------|
| ONCAP Admin System      | Member census, employer registry     | Fixed-width `.DAT`, csv | Monthly / on-change |
| ONCAP Financial System  | Contributions, payments              | Pipe-delimited `.TXT` | Per pay cycle       |
| ONCAP Events Module     | Life events (buyback, beneficiary)   | Pipe-delimited `.TXT` | Monthly batched     |
| Member Portal           | Portal activity                      | JSONL                 | Daily feed, monthly consolidated |
| Contact Center          | Call logs                            | CSV                   | Monthly             |
| Event Registration      | Seminar attendance                   | CSV                   | Annual              |
| Email Platform          | Email engagement                     | CSV                   | Monthly             |

---

## 11. Governance & Compliance

**Data classification**: All member data is **confidential**. In production,
this would include:

- SIN (masked in analytics)
- Date of birth
- Home address
- Salary information

**In this synthetic project**: All data is **generated**. Any resemblance to
real persons or organizations is coincidental.

**Regulatory requirements modeled**:

- Annual statements to members (regulatory deadline)
- Actuarial valuation every 3 years
- Monthly financial reporting to Trustees

---

## Appendix A: Change History

| Version | Date       | Change                                      |
|---------|------------|---------------------------------------------|
| 1.0     | 2024-01-31 | Initial version for Week 1 synthetic build. |