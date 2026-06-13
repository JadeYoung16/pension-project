# Week 4 Retrospective (2026-05-16 ~ 2026-05-25)

## Summary

Week 4 = data warehouse layer (Snowflake setup + ingestion + dbt staging).
Started from "Postgres data + loaders" (end of Week 3); ended with
"layered dbt project on top of Snowflake raw with 117 data quality
tests, ready for marts layer."

End state: 8 staging views + dbt-utils + tests + PII metadata pattern +
graceful warn handling for 3 known generator issues.

## What Went Well

1. **A/B/C case normalization taxonomy** — established Day 6, applied
   consistently across all 8 staging models. New model = classify each
   field, behavior follows. Codified design principle, reused
   reliably.

2. **dbt test as raw-data quality discovery** — 4+ raw schema
   surprises caught by failing tests at staging:
   - sex_code has 3 values not 2 (StatCan codeset)
   - status_code has 5 values not 2
   - member_census is monthly snapshot (composite PK needed)
   - transaction_id has 3 duplicates (generator bug)
   - pay_period_start 2% NULL
   - t3010 dual-format category codes
   - 8 orphan BNs in schedule3
   
   Each was caught at staging, not silently propagated to mart.

3. **PII metadata pattern + roadmap awareness** — 10+ columns flagged
   with contains_pii / pii_type / sensitivity. Roadmap (Snowflake
   masking + RBAC) not yet built but architectural awareness shown.

4. **Progressive depth via questions** — each conceptual question
   pulled deeper understanding (case principles, identifier vs enum,
   normalization, grain, dirty data layers, role differences). Building
   intuition incrementally beats memorizing patterns.

5. **dbt-utils integration timing** — installed in Day 7 not Day 6.
   Got minimum-viable dbt working first, then added community standard
   layer. Bootstrap discipline.

## What Didn't Go Well

1. **YAML inline comment bug** — pasted prose-style "<- new location"
   markers from mentor message broke dbt parser. Lost ~15 min
   debugging. Lesson: code blocks must be paste-ready; mentor must
   use yaml `#` for inline comments going forward.

2. **NULL check incomplete on transaction** — only verified pay_date
   NULL, missed pay_period_start which was 2% NULL. Cost ~10 min and
   one wrong yaml version. Lesson: NULL check all columns or none,
   no selective sampling.

3. **dbt selector syntax confusion** — `--select stg_external` doesn't
   work as schema selector. Correct syntaxes: `path:`, wildcard, name
   list. Should have learned from documentation, not trial-and-error.

4. **Test-before-run silent ERROR cascade** — running `dbt test` on
   model that hasn't been `dbt run` shows confusing "Object does not
   exist" errors. Mental model: run then test.

5. **3 versions on member_census yaml** — Day 6 v1->v2->v3->v4 due to
   guessing accepted_values values from sample data instead of running
   DISTINCT first. Eventually internalized "validate enums via DISTINCT
   BEFORE writing yaml". Same pattern not repeated in Days 7+.

## What's Still Ambiguous

1. **t3010 line item semantic naming** — line_300, line_305, etc. are
   CRA form line numbers. Need to consult CRA T3010 form spec (publicly
   available) to map line numbers to semantic names (e.g.
   total_full_time_positions). Deferred to Week 6.

2. **transaction <-> life_event lifecycle gap** — life_event has 8,254
   BBK_INSTALLMENT_PAY events but transaction has 0 BBK contribution_type
   rows. Generator gap; should produce paired records. Backlog.

3. **portal_event 1.8% missing rows** — TRY_PARSE_JSON re-ingestion to
   recover, but priority unclear. Backlog.

4. **Snowflake masking policy + RBAC scope** — PII metadata pattern
   established at staging, but actual masking/access controls not yet
   built. Week 9 polish.

5. **Macro for pay_frequency case mapping** — duplicated SQL between
   stg_oncap__employer_registry and stg_oncap__transaction. Should
   refactor to shared macro. Week 5 first-day candidate.

## Key Decisions Made

| Decision | Why |
|---|---|
| Case normalization A/B/C taxonomy | Single set of rules across 8 models |
| PII metadata via config.meta | Programmatic identification surface |
| Staging strict 1:1 with raw, no dedup | Hide nothing from downstream |
| dbt test warn + threshold (not error) | Pipeline runs but signals stay visible |
| t3010 minimal rename in staging | Defer semantic rename to mart with form spec |
| VARIANT preserved in portal_event | Variable schema per event_type, flatten in mart |
| ltrim leading zeros on t3010 category | Format normalization, not business rule |
| dbt-utils Week 4 not Week 5 | Production-standard package, simple to add |

## Career Path Recalibration

Mid-week clarification: target job = Analytics Engineer (not Data Engineer
or Marketing Analyst). Project alignment:

- Day 5 (Python loader, COPY INTO) = DE work — supporting context,
  not primary narrative
- Day 6-7 (dbt staging, tests, data modeling) = AE work — primary
  narrative
- Salesforce / GA / HubSpot skills not covered (would need separate
  marketing project)

Decision: stay AE-focused. Project is well-aligned for AE roles.

## Numbers

- 7 days planned, 9 calendar days actual (Sat-Sun-Mon spread)
- 4-5h/day estimated, 5-7h/day actual
- Buffer +0.7 days at start → 0.0 days at end (Week 4 on time)
- ~485k raw rows transformed across 8 staging models
- 117 data quality tests
- 3 known issues documented + tracked + thresholded


# Week 5 Retrospective

**Period**: 2026-05-26 – 2026-06-02
**Status**: Complete

## What was built

### Day 1 — Macro refactor
- Extracted `pay_frequency_label` macro from `stg_oncap__employer_registry`
  and `stg_oncap__transaction` (DRY refactor)
- Discovered latent bug: transaction-side mapping was missing `lower()` that
  employer-side had; centralized defensive normalization in the macro
- dbt test baseline held: PASS=114 WARN=3 ERROR=0 before and after

### Day 2–3 — Mart layer architecture design
- Created `docs/_marts_design.md` as the marts build anchor (9 sections)
- Decision #1: Kimball star schema
- Decision #2: surrogate key via `dbt_utils.generate_surrogate_key`
- Decision #3: layer-specific materialization (dim=table, fct=incremental/table by size)
- Decision #4: SCD strategy locked for all dims
  - dim_member: 3×SCD0, 4×SCD2, 5×SCD1 (enrollment_date → Type 1)
  - dim_employer, dim_charity, dim_date: fully designed
- Fact table candidates: 7 fct tables with grain + event-time semantics defined

### Day 4–5 — CI/CD Tier 1
- PR #3: GitHub Actions workflow — `dbt parse` on every PR
- PR #4: sqlfluff lint added to CI workflow + `.sqlfluff` project config
- 10 staging models style-cleaned to pass sqlfluff rules
- `_properties.yml` stray character fixed

## What went well
- Design-first discipline: 2 full days of architecture decisions before writing
  any mart SQL paid off — `_marts_design.md` is a complete build spec
- CI is now guarding every PR: dbt parse + sqlfluff lint both active
- Git workflow via PR branches practiced end-to-end (5 PRs merged)

## What was harder than expected
- sqlfluff rule tuning took longer than expected — several staging models needed
  non-trivial reformatting to satisfy L010/L028/L036
- Week 5 spanned more calendar days than planned (5/26–6/02 vs 5/26–5/31)

## Carry-forward into Week 6
- `dbt compile` + GitHub Secrets (Snowflake credentials) not added to CI yet —
  deferred as P1, can be done in Week 6 if time allows
- `_marts_design.md` is the anchor: Week 6 is mechanical translation into SQL

## Week 6 entry point
- `git log` HEAD: `d87a52b` (docs update)
- `origin/main`: `1bbf6a8` (PR #4 sqlfluff)
- Local ahead by 1 commit (docs), not yet pushed
- dbt parse: PASS (2 unused config warnings, known/harmless)
- Next action: Week 6 Day 1 — dbt snapshot infrastructure for SCD2 dims

# Week 7 Retrospective

**Period**: 2026-06-[填] – 2026-06-13 (Step A–B; week ongoing)
**Status**: Core complete (naive DAG orchestrating load + dbt, end-to-end green).
            Cosmos rewrite + CI push-trigger = optional carry-forward.

## Summary

Week 7 = Airflow orchestration. Goal locked up front: "naive linear DAG
first to learn the mechanics, Cosmos later if time allows." Went from
"loaders + dbt both key-pair, manually run piece by piece" to "Airflow
runs the full Snowflake load + dbt chain end-to-end, four tasks green."

Approach A-1: Airflow stays dumb (no dbt/creds installed); it mounts the
host docker socket and `docker exec`s into pension-app, where dbt +
Snowflake key-pair already live. The first real DAG run flushed out three
latent bugs that manual, piecemeal runs had been hiding — which became the
week's central lesson.

## What Went Well

1. **A-1 socket model held up cleanly** — airflow → docker socket → host
   daemon → pension-app → dbt verified before writing any DAG. Decoupling
   means airflow holds no credentials and can restart without touching a
   running dbt job. The `user: root` choice (for socket access) was clean
   here precisely because only the read-only dags dir is bind-mounted and
   all writable state lives in a named volume — no root-owned files leak
   into the repo.

2. **Naive-first discipline paid off** — resisted Cosmos/K8s scope creep.
   Building the simplest thing that works (4 BashOperators, `>>`) made the
   mechanics legible: Operator/task/DAG, schedule/catchup/start_date,
   retries vs idempotency are now understood, not memorized.

3. **Orchestration earned its keep on day one** — the full `dbt test`
   (201 tests, vs piecemeal `--select` runs) immediately surfaced a broken
   test config that had been latent for 4 days. This is the core argument
   for orchestration/CI over manual runs: forced full execution reveals
   local rot.

4. **Debugged by reading truth, not guessing** — every step resolved via
   cat / grep / git log / information_schema, not assumption. Several
   working hypotheses (MFA hang, stale target, "load history expired") were
   wrong and got overturned by actual data. `git log -L` pinned the exact
   commit that introduced the bad test value. Code/git is truth beat memory
   repeatedly — including correctly trusting "I remember this test passing."

## What Didn't Go Well

1. **dbt incremental schema drift** — deleting `1 as event_count` from
   fct_email changed only the .sql; the physical Snowflake table kept the
   EVENT_COUNT column. Incremental builds the insert column-list from the
   *target table*, so the new SELECT (minus the column) hit
   `invalid identifier 'EVENT_COUNT'`. Cost a long detour (chased MFA and
   stale-target theories first). Fix: `--full-refresh`. Lesson: changing an
   incremental model's schema needs a planned full-refresh or
   `on_schema_change` — editing SQL alone is not enough.

2. **COPY INTO double-load (raw ×2)** — raw was never truncated; COPY only
   appends and dedup relied entirely on Snowflake load history. Load history
   keys on file MD5, and `AUTO_COMPRESS=TRUE` re-gzips on every PUT, writing
   a fresh timestamp into the gzip header → same content, different MD5 →
   load history bypassed → every file loaded twice → event_id no longer
   unique → fct_email unique test failed (227502 dupes). Fix: explicit
   `TRUNCATE` before each COPY, making reload deterministic instead of
   renting idempotency from a fragile load-history mechanism.

3. **Latent broken test config (`config0`)** — a stray non-numeric token in
   `accepted_range.min_value` on fct_transaction, introduced during the
   803e757 config refactor (6-9), sat unexecuted for 4 days because manual
   runs never selected that test. Fixing one config bug had quietly planted
   another. Surfaced only when airflow ran the full suite. Fix:
   `min_value: 0` (contributions non-negative).

4. **CI bypassed by direct push to main** — CI is PR-gated
   (`on: pull_request`), so today's direct pushes to main ran no CI at all.
   Today's changes (config0 fix, TRUNCATE) reached main unvalidated by the
   pipeline. The squash-merge PR discipline exists precisely to prevent this.

## What's Still Ambiguous / Carry-forward

1. **Cosmos rewrite** — explode the single dbt_run black-box task into
   per-model Airflow tasks (DbtTaskGroup). Optional, planned "if time."

2. **CI should also trigger on push to main** — add `push: branches:[main]`
   to the workflow `on:` so direct pushes are gated too. Small, deferred.

3. **Executor upgrade** — standalone + SQLite → LocalExecutor + reuse the
   existing postgres metadata backend. More production-like; interview point.

4. **Two known COPY rejects (unchanged, pre-existing)** — transaction
   errors_seen=18 (1/file, looks like a SKIP_HEADER=2 boundary effect),
   portal_event errors_seen=5 (documented under-load by design). Not
   investigated this week; not related to the email duplication.

5. **`on_schema_change` on incremental models** — consider adding to
   fct_email / fct_transaction to harden against future column drift.
   Trade-offs to weigh; not auto-added.

## Key Decisions Made

| Decision | Why |
|---|---|
| A-1: socket + `docker exec` into pension-app | Airflow stays dumb/credential-free; reuse app's dbt + key-pair |
| `docker exec pension-app` (not `docker compose exec app`) | Container name needs no compose context; one dependency (socket) not four |
| docker-ce-cli from Docker's apt repo (not debian docker.io) | docker.io CLI speaks API 1.41; Docker Desktop daemon needs ≥1.44 |
| airflow standalone + SQLite (not LocalExecutor+postgres) | Naive-first; sequential DAG doesn't need parallelism |
| schedule=None, catchup=False, fixed past start_date | Manual debug phase; catchup-storm guard is reflexive |
| 4 BashOperators, linear `>>` | Each step consumes the prior's output → hard serial |
| retries=2 on all tasks | Astronomer min for dbt tasks; all 4 sufficiently idempotent |
| TRUNCATE+COPY (not append-only + staging dedup) | Not true incremental ingest — periodic full reload; deterministic |

## Numbers

- Step A–B done on 2026-06-12/13; full Week 7 window targets ~6-27
- Three latent bugs surfaced by first full orchestrated run:
  schema drift (fct_email), COPY ×2 (raw), broken test config (fct_transaction)
- email_engagement: 455004 → 227502 rows after TRUNCATE+COPY (back to single)
- dbt test: 201 tests; final run green (PASS, 4 warnings non-blocking)
- 6 commits pushed to main (key-pair → infra → load idempotency → config0 → DAG)