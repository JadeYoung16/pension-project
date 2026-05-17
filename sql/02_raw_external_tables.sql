-- =============================================================================
-- raw_external — landing tables for third-party reference data
-- =============================================================================
-- Conventions (same as raw_oncap, restated for self-containment):
--   * Column names match the source file exactly (case preserved as lowercase
--     by Postgres; mixed-case source headers like "Legal Name" stored as
--     "legal_name" via snake_case rewrite below).
--   * CRA T3010 Schedule 3 has numeric column names ("300", "370", etc.)
--     for line-item codes from the charity return form. These are quoted
--     with double quotes per Postgres rules and kept as-is in raw —
--     business-meaning renames (e.g. "300" → ft_employee_count) happen
--     in stg_external (Week 5).
--   * All columns TEXT in raw. Type coercion deferred to staging.
--     CRA data has known quality issues (suspect FT counts in religious
--     categories, blanks, etc.) — TEXT prevents load-time failures.
--   * Same audit triplet as raw_oncap: _source_file / _row_num / _loaded_at
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Table 1: t3010_ident  ←  ident_2023_update.csv (national, full file)
-- -----------------------------------------------------------------------------
-- Source: CRA T3010 charity return identification info (2023 reporting year).
-- We ingest the full national file; Ontario filtering happens in
-- stg_external.stg_t3010_ident (province = 'ON').
-- The project-internal ident_2023_ontario.csv is only used by the employer
-- generator (upstream simulator) and is NOT loaded by the loader.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_external.t3010_ident (
    bn                   TEXT,
    category             TEXT,
    sub_category         TEXT,
    designation          TEXT,
    legal_name           TEXT,
    account_name         TEXT,
    address_line_1       TEXT,
    address_line_2       TEXT,
    city                 TEXT,
    province             TEXT,
    postal_code          TEXT,
    country              TEXT,
    -- audit columns
    _source_file         TEXT   NOT NULL,
    _row_num             BIGINT NOT NULL,
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw_external.t3010_ident IS
    'CRA T3010 charity identification (2023). National scope. Source: ident_2023_update.csv. Encoding: utf-8-sig (BOM-prefixed UTF-8).';

-- -----------------------------------------------------------------------------
-- Table 2: t3010_schedule3  ←  schedule_3_compensation_2023.csv (national)
-- -----------------------------------------------------------------------------
-- Source: CRA T3010 Schedule 3 — compensation and employee counts.
-- Numeric column names ("300", "305", ..., "390") are CRA form line codes:
--   300 = permanent full-time compensated positions
--   305-345 = compensation range buckets (head counts in salary bands)
--   370 = part-time or part-year employees
--   380 = total compensation paid (line 390 = ten highest-paid)
--   390 = ten highest-compensated positions
-- Quoted with double quotes per Postgres requirement for non-identifier names.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_external.t3010_schedule3 (
    bn          TEXT,
    fpe         TEXT,                 -- Fiscal Period End (YYYY-MM-DD)
    form_id     TEXT,
    "300"       TEXT,
    "305"       TEXT,
    "310"       TEXT,
    "315"       TEXT,
    "320"       TEXT,
    "325"       TEXT,
    "330"       TEXT,
    "335"       TEXT,
    "340"       TEXT,
    "345"       TEXT,
    "370"       TEXT,
    "380"       TEXT,
    "390"       TEXT,
    -- audit columns
    _source_file  TEXT   NOT NULL,
    _row_num      BIGINT NOT NULL,
    _loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw_external.t3010_schedule3 IS
    'CRA T3010 Schedule 3 compensation (2023). National scope. Source: schedule_3_compensation_2023.csv. Numeric column names are CRA line codes; renamed to business-friendly names in stg_external.';