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