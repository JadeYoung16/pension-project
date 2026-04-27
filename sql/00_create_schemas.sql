-- =============================================================================
-- pension-project — Postgres schema creation
-- =============================================================================
-- Naming convention: <layer>_<source>
--   raw_oncap   — landing zone for the OnCap admin system files (this layer)
--   stg_oncap   — dbt staging models (cleaned, typed, deduped)  [Week 4+]
--   mart_oncap  — dbt mart models (dimensional / business layer) [Week 6+]
--
-- Why vendor-suffixed?  If we add another source (CRA T3010, UCI), it'll get
-- its own raw_<source> / stg_<source> / mart_<source> rather than colliding.
--
-- Run with:
--   psql -f sql/00_create_schemas.sql
-- or via the loader's --init flag.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_oncap;
CREATE SCHEMA IF NOT EXISTS stg_oncap;
CREATE SCHEMA IF NOT EXISTS mart_oncap;

COMMENT ON SCHEMA raw_oncap  IS 'Landing zone — faithful mirror of OnCap admin system files. Truncate-and-load (Week 3-4). Append + MERGE (Week 5+ in Snowflake).';
COMMENT ON SCHEMA stg_oncap  IS 'dbt staging — cleaned, typed, deduped, source-aligned.';
COMMENT ON SCHEMA mart_oncap IS 'dbt marts — dimensional model, business-facing tables.';

