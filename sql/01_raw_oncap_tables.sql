-- =============================================================================
-- raw_oncap — landing tables for OnCap admin system files
-- =============================================================================
-- One table per source file type.  Conventions:
--   * Column names match the source file exactly (case-insensitive in Postgres,
--     stored as lowercase).
--   * Codes / IDs / postal-code-like fields use TEXT, even when they look numeric.
--   * Real numeric measurements (counts, money) get a real numeric type.
--   * Three audit columns at the end of every table:
--       _source_file  — basename of the file this row came from
--       _row_num      — 1-indexed line number in the source file
--       _loaded_at    — wall-clock at COPY time (defaulted by the database)
--   * No PK, no NOT NULL.  Raw mirrors the source faithfully, including its
--     duplicates and nulls.  PKs and constraints belong in stg_oncap (Week 4).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Table 1: employer_registry  ←  ONCAP001_EMPLOYER_REGISTRY_YYYYMMDD.csv
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_oncap.employer_registry (
    employer_id                      TEXT,
    business_number                  TEXT,
    legal_name                       TEXT,
    operating_name                   TEXT,
    sector_category_code             TEXT,
    city                             TEXT,
    postal_code                      TEXT,
    employer_size_band               TEXT,
    employee_count                   INTEGER,
    enrolled_member_count            INTEGER,
    pay_frequency                    TEXT,
    participation_start_date         DATE,
    plan_administrator_name          TEXT,
    plan_administrator_email         TEXT,
    status                           TEXT,
    -- audit columns
    _source_file                     TEXT   NOT NULL,
    _row_num                         BIGINT NOT NULL,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);