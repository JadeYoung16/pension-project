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
## Decision #4: SCD strategy per dimension

*To be filled — Day 3.*

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
## Candidate fact tables

*To be filled — Day 2 Step 4.*

---

<a name="event-time"></a>
## Event-time semantics & late-arriving handling

*To be filled — Day 3. See concept discussion in Week 5 Day 2 chat
for full taxonomy (3-tier event-time data quality framework).*

---

<a name="er-diagram"></a>
## ER diagram

*To be filled — Day 3. Tool: DBML or Mermaid (decision pending).*

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