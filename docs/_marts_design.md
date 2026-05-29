# Marts Layer Design — pension_dwh

**Status:** In progress (Week 5 Day 2 onwards)
**Last updated:** 2026-05-26
**Lock:** Decision #1 locked Week 5 Day 2. Decisions #2–#4 in progress.

This document is the **single source of truth** for marts layer
architectural decisions. It captures the *why* behind structural
choices that the SQL files themselves cannot express.

Every architectural decision below is **explicit and reversible
cost-aware**: each entry states what was chosen, what was rejected,
the reasoning, and the cost of reversal.

---

## Table of Contents

1. [Decision #1: Dimensional modeling methodology (Kimball)](#decision-1)
2. [Decision #2: Surrogate key strategy](#decision-2) — *Day 2 Step 3*
3. [Decision #3: Materialization strategy](#decision-3) — *Day 2 Step 3*
4. [Decision #4: SCD strategy per dimension](#decision-4) — *Day 3*
5. [Candidate dimension tables](#dim-candidates) — *Day 2 Step 4*
6. [Candidate fact tables](#fct-candidates) — *Day 2 Step 4*
7. [Event-time semantics & late-arriving handling](#event-time) — *Day 3*
8. [ER diagram](#er-diagram) — *Day 3*
9. [Open questions / deferred decisions](#open)

---

<a name="decision-1"></a>
## Decision #1: Dimensional modeling methodology — Kimball

**Decision:** Adopt Kimball dimensional modeling. Marts layer will
be organized as star schemas with conformed dimensions, evolving
into a galaxy/constellation as fact tables accumulate across
business processes.

**Rejected alternative:** Inmon 3NF enterprise data warehouse.

### Rationale

**1. Cloud warehouse economics inverts Inmon's storage argument.**
Inmon's primary value proposition in the 1990s was minimizing
storage through strict 3NF normalization. In a Snowflake/BigQuery
era where storage is ~$23/TB/month and compute is the dominant
cost line, denormalized dimensions reduce join cost — which more
than offsets the marginal storage premium. Kimball "wastes" storage
to save compute, and cloud pricing structurally favors that trade.

**2. dbt is mart-oriented by design.**
dbt's `ref()` graph, materialization model (view/table/incremental),
and project conventions all assume a model-per-mart workflow.
Implementing Inmon's central 3NF EDW in dbt is possible but
swims against the framework's grain. Kimball is dbt-native.

**3. BI tool compatibility.**
Looker (LookML), Tableau (data source modeling), Power BI (semantic
model), and Metabase all assume star schema as the default join
topology. SCD2 + natural key + range join is not a JOIN pattern
these tools generate from drag-and-drop interfaces. Choosing
Kimball preserves downstream tooling flexibility.

**4. Time-to-value.**
Inmon's top-down EDW-first approach defers business value until
the central warehouse is built. For a portfolio project (and for
real-world teams under quarterly pressure), Kimball's bottom-up
mart-by-mart delivery is the only viable cadence.

**5. Conformed dimensions handle cross-process analytics.**
The historical critique of Kimball — that disconnected marts
prevent cross-business-process analysis — is solved by conformed
dimensions: `dim_member`, `dim_employer`, `dim_date`, `dim_charity`
are shared across all fact tables, enabling questions like
"do members with high portal engagement contribute more?" without
needing a 3NF central layer.

### Implications for downstream structure

- `models/marts/` will contain `dim_*` and `fct_*` only — no
  normalized intermediate tables.
- Staging layer (`stg_*`) remains 1:1 mirror of raw with minimal
  transformations; it is **not** a 3NF normalization layer.
- Cross-mart analyses go through conformed dimensions, not through
  a hidden central table.

### Reversal cost

**Prohibitive.** Reversing this decision after Week 6 requires:
- Rewriting all `dim_*` / `fct_*` models as normalized tables
- Re-designing all downstream BI dashboards
- Re-training any analysts trained on star schema patterns

**Decision is treated as locked.** Reconsideration requires explicit
stakeholder review and a cost-justified reason.

### Industry reference

- *The Data Warehouse Toolkit* (Kimball & Ross, 3rd ed., 2013) —
  canonical reference
- dbt Labs blog: "How we structure our dbt projects" (2021) — 
  documents Kimball as community default
- Locally: Snowflake's own QuickStart tutorials assume Kimball

---

<a name="decision-2"></a>
## Decision #2: Surrogate key strategy

**Decision:** Use `dbt_utils.generate_surrogate_key` (MD5) for all
surrogate keys. Naming convention `<entity>_sk`. Natural keys
preserved alongside in dim tables. Fact tables bind sk at ETL
load time via dim lookup (not at query time).

**Status:** Locked at Week 5 Day 2 (2026-05-26). Per-dim input
column composition (sub-decision 2d) finalized Day 3 with SCD
strategy.

### Sub-decisions

| # | Choice | Locked value | Rejected alternative |
|---|---|---|---|
| 2a | Hash algorithm | MD5 (dbt_utils default) | SHA-256 (no practical benefit); sequence int (breaks cross-env reproducibility) |
| 2b | Naming convention | `<entity>_sk` | `_key` (ambiguous with natural key colloquialism); `_pk` (uncommon) |
| 2c | Natural key preservation | Keep both in dim | Sk-only (loses debug-ability and BI compatibility) |
| 2d | Sk input columns | Per-dim, Day 3 lock | One-size-fits-all (doesn't fit Type 0/1 vs Type 2 dims) |
| 2e | Fct sk binding timing | ETL load time | Query-time range join (loses temporal consistency, BI tools can't generate) |

### Rationale

**MD5 over alternatives:**
- dbt_utils default, zero-friction adoption
- 32-char hex, stable across dev/prod/CI environments — critical
  for regression testing
- Non-cryptographic use; collision attacks irrelevant
- At project scale (max ~1M rows/dim), collision probability is
  effectively zero
- Sequence int breaks cross-environment reproducibility (same
  logical row gets different sk in dev vs prod)
- Cost: 32 bytes per sk × ~1M rows = ~32MB extra per large dim,
  trivial at Snowflake pricing

**Natural key preservation:**
- Debug-ability: analysts can read `member_id` in WHERE clauses
  without joining dim
- BI tool friendliness: some tools assume natural keys exist
- Upstream integration: external systems (Salesforce, oncap source
  system) reference natural keys
- Cost: 8-16 bytes/row, ~1.6MB for `dim_member`, negligible

**Fct binds sk at ETL load time:**
- Range join executed once at fct build (dbt incremental run),
  not on every analyst query
- Result is **temporal consistency**: fct rows are immutable
  historical references to dim state at event time. Query results
  reproducible regardless of when query is run.
- All downstream queries become equality joins (`on fct.sk = dim.sk`),
  enabling BI tool auto-generation
- Cost: dim must build before fct; dbt DAG handles this via `ref()`

### Implementation pattern (Week 6 preview)

```sql
-- Fct model binds sk via range join at build time
select
    t.*,
    m.member_sk,
    e.employer_sk
from {{ ref('stg_oncap__transaction') }} t
left join {{ ref('dim_member') }} m
    on t.member_id = m.member_id
    and t.event_date >= m.valid_from
    and t.event_date <  coalesce(m.valid_to, '9999-12-31')
left join {{ ref('dim_employer') }} e
    on t.employer_id = e.employer_id
    and t.event_date >= e.valid_from
    and t.event_date <  coalesce(e.valid_to, '9999-12-31')
```

For SCD2 dims, dbt snapshots auto-generate `dbt_scd_id` from
`(unique_key, dbt_valid_from)`. The dim layer renames this to
`<entity>_sk` for naming consistency.

### Reversal cost

**Medium.** Reversing requires:
- Changing fct schema to drop sk columns and add natural-key FK
- Rewriting downstream queries to use range join semantics
- Likely breaks BI dashboards built on equality-join assumption

Can be reversed if discovered necessary before heavy BI buildout
(Week 7+). After dashboard layer is in place, reversal is
prohibitive.

---

<a name="decision-3"></a>
## Decision #3: Materialization strategy

**Decision:** Layer-specific materialization. Staging = view.
Snapshots = table (dbt-managed). Dims = table. Facts split by
size: large event streams (>100K rows) use incremental with
look-back window; small event streams (<100K rows) use table.

**Status:** Locked at Week 5 Day 2 (2026-05-26). Per-fact
look-back window finalized Day 3 with event-time semantics.

### Sub-decisions

| Layer | Materialization | Rationale |
|---|---|---|
| `stg_*` | view | Light transformations; want raw-fresh semantics; no storage duplication. (Already default since Week 4 Day 6.) |
| `snapshots/*` | table (dbt-managed) | dbt convention; no real choice |
| `dim_*` | table | Cloud warehouse: storage cheap, compute expensive. Build-once query-many wins. All dims <1M rows, full rebuild <60s. |
| Large `fct_*` (>100K) | incremental | Compute savings on rebuild. Append-only event streams natural fit. Look-back window handles late-arriving. |
| Small `fct_*` (<100K) | table | Full rebuild cheap; incremental complexity (unique_key config, look-back logic, `is_incremental()` branches) not justified. |

### Per-fact materialization plan

Based on raw layer row counts and expected growth rates:

| Candidate fact table | Raw rows | Growth rate | Materialization |
|---|---|---|---|
| `fct_email_send` | 227K | High (monthly campaigns) | incremental |
| `fct_email_event` | TBD (verify Day 3) | Very high (multi-event per send) | incremental |
| `fct_transaction` | 190K | Medium (monthly pay cycles) | incremental |
| `fct_portal_event` | 58K | High (daily activity) | incremental |
| `fct_life_event` | 18K | Low | table |
| `fct_seminar_attendance` | 6K | Low | table |
| `fct_call` | 4K | Medium | table |

### Threshold heuristic

~100K rows is approximate breakeven between table and incremental.
Below: table simpler, full rebuild fast, no state to maintain.
Above: incremental's compute savings outweigh complexity cost.

`fct_portal_event` at 58K is below threshold today but expected
to grow rapidly (portal is active product) — pre-emptively
incremental to avoid future migration.

### Incremental configuration template (Week 6 preview)

```sql
{{ config(
    materialized='incremental',
    unique_key='<entity>_sk',
    on_schema_change='fail',
    incremental_strategy='merge'
) }}

select ...
from {{ ref('stg_oncap__<source>') }} t
left join {{ ref('dim_member') }} m on ...

{% if is_incremental() %}
  where t.event_date >= (
      select dateadd(day, -<lookback>, max(event_date)) from {{ this }}
  )
{% endif %}
```

**Look-back window** protects against late-arriving data. Per-fact
windows locked Day 3 based on event-time semantics (e.g., 7 days
for email, 30 days for life_event, 1 day for portal).

### Reversal cost

**Low.** Changing materialization is a config-level change with
no schema impact. Can re-materialize any model with `dbt run
--full-refresh` at any time. Decisions can be revisited per-model
if performance or freshness assumptions change.

---

<a name="decision-4"></a>
**Decision:** SCD strategy assigned per dimension, and per column
for the two SCD2 dimensions. Locked Week 5 Day 3.

### dim_member — SCD2 row-versioning

| Column | SCD type | Reasoning |
|---|---|---|
| member_id | 0 | Natural key, immutable |
| date_of_birth | 0 | Birth date never changes |
| member_status | 2 | active→terminated must retain history |
| salary_band | 2 | Raises/cuts versioned so facts bind correct period |
| employer_id | 2 | Employer change must retain history |
| marital_status | 2 | Status change must retain history |
| enrollment_date | 1 | Type 0 in principle, but allow correction of data-entry errors |
| first_name, last_name | 1 | Name change — latest value only |
| email | 1 | Latest value only |
| postal_code | 1 | Move — latest value only |
| gender | 1 | Overwrite |

Summary: 3 SCD0 / 4 SCD2 / 5 SCD1.

### dim_employer — SCD2 row-versioning

| Column | SCD type | Reasoning |
|---|---|---|
| employer_id | 0 | Natural key |
| business_number | 0 | CRA business number, fixed identifier |
| participation_start_date | 0 | Plan-join date, historical fact |
| acquisition fields | 0 | Historical M&A facts |
| employer_status | 2 | active→withdrawn must retain history |
| size_band | 2 | Band changes must retain history |
| sector_category_code | 2 | Sector reclassification must retain history |
| pay_frequency | 2 | Affects transaction interpretation, versioned |
| legal / operating name | 1 | Latest value only |
| administrator info | 1 | Overwrite |
| city, postal_code | 1 | Relocation — latest value only |

Summary: 4 SCD0 / 4 SCD2 / 3 SCD1.

### dim_charity — Yearly partition (not SCD2)

Grain: one row per charity per fiscal year. PK: MD5(bn_number +
fiscal_year_end). CRA T3010 data is an annual filing whose measures
(revenue, expenses, assets) change every year; SCD2 would collapse
into a yearly partition anyway but at higher query cost (range join
vs `where fiscal_year = N` equality filter). Source is annual by
nature, so the dimension partitions by year to match.

### dim_date — Static, no versioning

Generated via `dbt_utils.date_spine`; no source table, no version
changes. PK: integer smart key `YYYYMMDD` (the one Kimball-sanctioned
meaningful key — immutable, human-readable, no SCD2 dedup need so the
Decision #2 MD5 rule does not apply here). Fiscal year/quarter follow
Canadian government year (Apr 1 – Mar 31), aligning with CRA and
regulatory reporting.

---

<a name="dim-candidates"></a>
## Candidate dimension tables

<a name="dim-candidates"></a>
## Candidate dimension tables

| Dim | Grain | Est. rows | SCD pattern | Source |
|---|---|---|---|---|
| `dim_member` | One row per member version | ~500K | SCD2 | `stg_oncap__member_census` |
| `dim_employer` | One row per employer version | ~800 | SCD2 | `stg_oncap__employer_registry` |
| `dim_charity` | One row per charity per fiscal year | ~425K | Yearly partition | `stg_external__cra_t3010_*` |
| `dim_date` | One row per calendar day | ~7,670 | Static | Generated (`dbt-utils.date_spine`) |

### dim_member

- **Grain:** One row per member per SCD2 version.
- **PK:** `member_sk` (MD5 of `member_id` + `dbt_valid_from`)
- **Natural key:** `member_id`
- **SCD type by column:**
  - **Type 0** (immutable): `member_id`, `date_of_birth`
  - **Type 1** (overwrite): `first_name`, `last_name`, `gender`,
    `email`, `phone`, `postal_code`, `city`, `province`,
    `beneficiary_name`, `beneficiary_relationship`
  - **Type 2** (track history): `member_status`, `employer_id`,
    `department`, `salary_band`, `annual_salary_cad`,
    `marital_status`, `enrollment_date`, `termination_date`
- **Design note — enrollment_date / termination_date are Type 2,
  not industry-default Type 0:** Operations reuses `member_id` on
  rehire (industry default issues a new id). On rehire,
  `enrollment_date` resets and `termination_date` clears, so both
  evolve and require history. Verified against business workflow.
- **Conformed:** Used by all 7 fact tables.

### dim_employer

*SCD design — Day 3.*

### dim_charity

*SCD design + yearly-partition vs SCD2 decision — Day 3.*

### dim_date

*Attribute list + fiscal-year definition — Day 3.*

---

<a name="fct-candidates"></a>
**Status:** Drafted Week 5 Day 2, event-time semantics and
per-fact look-back finalized Day 3.

### Overview

| Fct | Grain | Est. rows | Materialization | Late-arriving |
|---|---|---|---|---|
| fct_transaction | One pension contribution/withdrawal/transfer | 190K+ | incremental | 30d |
| fct_email_send | One email send event | 227K+ | incremental | 1d |
| fct_email_event | One email interaction (open/click/etc.) | ~400K+ | incremental | 7d |
| fct_portal_event | One portal user action | 58K+ | incremental | 1d |
| fct_call | One customer service call | 4K | table | — |
| fct_seminar_attendance | One member-seminar attendance | 6K | table | — |
| fct_life_event | One member life event | 18K | table | — |

### fct_transaction
- **Grain:** One pension contribution / withdrawal / transfer event
- **PK:** transaction_sk (MD5 of transaction_id)
- **FK:** member_sk, employer_sk, event_date_sk
- **Measures:** amount_cad, employee_contribution_cad, employer_contribution_cad
- **Degenerate dims:** transaction_type, pay_period_end_date, pay_frequency
- **Event-time:** event_date = pay_period_end_date
- **Materialization:** incremental, 30-day look-back
- **Open Q (Week 6):** transfer-in vs transfer-out sign convention

### fct_email_send
- **Grain:** One email send event (separate from open/click)
- **PK:** email_send_sk
- **FK:** member_sk, event_date_sk
- **Measures:** 1 (count)
- **Degenerate dims:** campaign_id, email_template_id, delivery_status
- **Event-time:** sent_at
- **Materialization:** incremental, 1-day look-back
- **Note:** campaign_id kept as DD; revisit dim_email_campaign in Week 6 if campaign attributes emerge

### fct_email_event
- **Grain:** One email interaction (open, click, unsubscribe, bounce)
- **PK:** email_event_sk
- **FK:** email_send_sk (link to fct_email_send), member_sk, event_date_sk
- **Measures:** 1 (count); time_since_send_minutes (derived)
- **Degenerate dims:** event_type, click_url
- **Event-time:** event_timestamp
- **Materialization:** incremental, 7-day look-back
- **Open Q (Week 6):** multiple opens per send — keep all (true measure) or dedupe to first

### fct_portal_event
- **Grain:** One portal user action (login, view, calculator, etc.)
- **PK:** portal_event_sk
- **FK:** member_sk, event_date_sk
- **Measures:** 1 (count)
- **Degenerate dims:** event_type, page_path, ip_hash, user_agent
- **Event-time:** event_timestamp
- **Materialization:** incremental, 1-day look-back (pre-emptive despite 58K size, given portal growth rate)
- **Open Q (Week 6):** flatten event_properties VARIANT or keep raw

### fct_call
- **Grain:** One customer service call
- **PK:** call_sk
- **FK:** member_sk, event_date_sk
- **Measures:** call_duration_sec
- **Degenerate dims:** call_topic, call_outcome, agent_id
- **Event-time:** call_started_at
- **Materialization:** table (4K rows, full rebuild trivial)
- **Note:** agent_id kept as DD (no stable describable attributes)

### fct_seminar_attendance
- **Grain:** One member-seminar attendance event
- **PK:** seminar_attendance_sk (MD5 of member_id + seminar_id)
- **FK:** member_sk, event_date_sk
- **Measures:** 1 (count)
- **Degenerate dims:** seminar_id, seminar_topic, delivery_mode
- **Event-time:** seminar_date
- **Materialization:** table (6K rows)
- **Note:** seminar_id kept as DD

### fct_life_event
- **Grain:** One member life event (marriage, birth, divorce, job change)
- **PK:** life_event_sk
- **FK:** member_sk, event_date_sk
- **Measures:** 1 (count)
- **Degenerate dims:** event_category, reporting_channel
- **Event-time:** event_date (often event_date ≪ loaded_at)
- **Materialization:** table (18K rows). Most late-arriving fact in the project; deliberately chose table over incremental to sidestep look-back complexity while size remains small.

---

<a name="event-time"></a>
**Three-tier time model.** Every fact distinguishes:
- **Event-time** — when the real-world event happened (e.g.
  `pay_period_end_date`, `event_timestamp`). This is the time used
  for `event_date_sk` and for incremental look-back.
- **Received-time** — when the source system recorded it.
- **Loaded-time** (`loaded_at`) — when our pipeline ingested it.

For late-arriving data, `event_time ≪ loaded_time`. Incremental
models must therefore look back from `max(event_date)` rather than
filter on load time, or late rows are silently dropped.

**Look-back window** applies only to incremental facts. Table-materialized
facts rebuild fully each run, so late-arriving rows are re-scanned
automatically — no window needed.

| Fct | Materialization | Event-time column | Look-back | Reasoning |
|---|---|---|---|---|
| fct_transaction | incremental | pay_period_end_date | 30d | Employer late/adjusted remittances; covers a full pay + reconciliation cycle |
| fct_email_event | incremental | event_timestamp | 7d | Opens/clicks reported with delay; covers the long tail |
| fct_email_send | incremental | sent_at | 1d | System-logged on send, rarely late; guards cross-midnight boundary |
| fct_portal_event | incremental | event_timestamp | 1d | Real-time clickstream; guards cross-midnight boundary |
| fct_call | table | call_started_at | — | Full rebuild, no window |
| fct_seminar_attendance | table | seminar_date | — | Full rebuild, no window |
| fct_life_event | table | event_date | — | Most late-arriving fact (members report marriages/births months later), but 18K rows — table full rebuild sidesteps look-back entirely |

**Incremental filter pattern (Week 6 implementation):**
```sql
{% if is_incremental() %}
  where event_date >= (
    select dateadd(day, -<lookback>, max(event_date)) from {{ this }}
  )
{% endif %}
```
---

<a name="er-diagram"></a>
## ER diagram

<a name="er-diagram"></a>
## ER diagram

**Approach:** No hand-drawn ER diagram is maintained in this repo.

**Rationale:** In a dbt-based stack, the authoritative structural
view is the lineage DAG produced by `dbt docs generate`, which is
derived directly from `ref()`/`source()` dependencies in the model
SQL. A machine-derived DAG stays consistent with code by
construction; a hand-drawn diagram (Mermaid/DBML) is manually
maintained and drifts as models change. Maintaining one would add a
stale-prone artifact rather than a source of truth.

**Where structure lives instead:**
- **Dimensional semantics** (which tables are dim vs fct, grain,
  conformed-dimension relationships) — captured in the *Candidate
  dimension tables* and *Candidate fact tables* sections above, plus
  per-model `description` fields landed in Week 6.
- **Dependency structure** (who refs whom) — auto-generated as a
  lineage DAG via `dbt docs generate` once models exist (Week 6).
  This is the project's "ER diagram" equivalent and updates
  automatically with the code.

**Note:** A formal, hand-produced ER diagram may be added late in the
project (post-implementation) if needed as a delivery/review artifact
for non-technical or compliance audiences — consistent with how
regulated-industry data teams treat ER diagrams as review
deliverables rather than design-time inputs. Deferred until then.

---

<a name="open"></a>
## Open questions / deferred decisions

- [ ] DBML vs Mermaid for ER diagram (Day 3)
- [ ] Whether to add `dim_call_center` / `dim_seminar` as standalone
      dims or fold attributes into degenerate dims on the fact
      side (Day 2 Step 4)
- [ ] How to handle `cra_t3010_*` annual snapshots —
      `dim_charity` SCD2 vs annual partitions (Day 3)
- [ ] Mini-dimension (Type 4) — confirmed not needed at current
      scale, revisit if `dim_member` row count exceeds 5M
- [ASSUMPTION] Re-enrollment issues a **new member_id** (no reuse).
  Consequence: multiple membership spells of the same natural person
  are independent members and cannot be aggregated across spells.
  enrollment_date stays Type 1 (handles employer data-entry
  corrections). Re-examine trigger: if a "per-person, across
  membership spells" analytical need arises, change dim_member grain
  to member × membership spell (add membership_sequence). Deferred —
  not in Week 5/6 scope.