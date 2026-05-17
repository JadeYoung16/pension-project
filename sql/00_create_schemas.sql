-- =============================================================================
-- pension-project — Postgres schema creation
-- =============================================================================
-- Naming convention: <layer>_<source>
--   raw_oncap     — landing zone for the OnCap admin system files
--   stg_oncap     — dbt staging (cleaned, typed, deduped)            [Week 4+]
--   mart_oncap    — dbt marts (dimensional / business layer)         [Week 6+]
--   raw_external  — landing zone for third-party reference data
--                   (CRA T3010 Ontario charity register)             [Week 4+]
--   stg_external  — dbt staging for external sources                 [Week 5+]
--   mart_external — dbt marts derived from external sources          [Week 6+]
--
-- Why vendor-suffixed?  If we add another source (UCI, etc.), it gets its own
-- raw_<source> / stg_<source> / mart_<source> rather than colliding.
--
-- Why external is a separate top-level family (not under raw_oncap)?
-- raw_<source> mirrors a system of record verbatim.  raw_oncap is the
-- pension admin system; raw_external is third-party reference data we
-- enrich with.  Different ingestion cadence, different ownership, different
-- contractual semantics.  Keeping them apart at the schema level keeps
-- the data lineage story clean (relevant for Week 9 sourcing doc).
--
-- Run with:
--   psql -f sql/00_create_schemas.sql
-- or via the loader's --init flag.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_oncap;
CREATE SCHEMA IF NOT EXISTS stg_oncap;
CREATE SCHEMA IF NOT EXISTS mart_oncap;

CREATE SCHEMA IF NOT EXISTS raw_external;
CREATE SCHEMA IF NOT EXISTS stg_external;
CREATE SCHEMA IF NOT EXISTS mart_external;

COMMENT ON SCHEMA raw_oncap     IS 'Landing zone — faithful mirror of OnCap admin system files. Truncate-and-load (Week 3-4). Append + MERGE (Week 5+ in Snowflake).';
COMMENT ON SCHEMA stg_oncap     IS 'dbt staging — cleaned, typed, deduped, source-aligned.';
COMMENT ON SCHEMA mart_oncap    IS 'dbt marts — dimensional model, business-facing tables.';

COMMENT ON SCHEMA raw_external  IS 'Landing zone — third-party reference data (CRA T3010, etc.). 1:1 mirror of source files.';
COMMENT ON SCHEMA stg_external  IS 'dbt staging — cleaned external sources, joinable to stg_oncap.';
COMMENT ON SCHEMA mart_external IS 'dbt marts — external-data-derived dims/facts (reserved for future).';
