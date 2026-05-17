-- =============================================================================
-- raw_external — landing tables for CRA T3010 (Snowflake)
-- =============================================================================
-- Translated from sql/02_raw_external_tables.sql.
-- Same conventions; column names with non-identifier syntax kept double-quoted.
-- =============================================================================

USE SCHEMA RAW_EXTERNAL;

-- -----------------------------------------------------------------------------
-- Table 1: t3010_ident
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS t3010_ident (
    bn                   STRING,
    category             STRING,
    sub_category         STRING,
    designation          STRING,
    legal_name           STRING,
    account_name         STRING,
    address_line_1       STRING,
    address_line_2       STRING,
    city                 STRING,
    province             STRING,
    postal_code          STRING,
    country              STRING,
    _source_file         STRING       NOT NULL,
    _row_num             BIGINT       NOT NULL,
    _loaded_at           TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'CRA T3010 charity identification (2023). National scope. Source: ident_2023_update.csv. Encoding: utf-8-sig (BOM-prefixed UTF-8).';

-- -----------------------------------------------------------------------------
-- Table 2: t3010_schedule3
-- -----------------------------------------------------------------------------
-- Numeric column names ("300", "305", ..., "390") are CRA form line codes.
-- Snowflake requires double-quoting (same as Postgres). Renames to
-- business-friendly names happen in stg_external (Week 5).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS t3010_schedule3 (
    bn          STRING,
    fpe         STRING,
    form_id     STRING,
    "300"       STRING,
    "305"       STRING,
    "310"       STRING,
    "315"       STRING,
    "320"       STRING,
    "325"       STRING,
    "330"       STRING,
    "335"       STRING,
    "340"       STRING,
    "345"       STRING,
    "370"       STRING,
    "380"       STRING,
    "390"       STRING,
    _source_file  STRING       NOT NULL,
    _row_num      BIGINT       NOT NULL,
    _loaded_at    TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'CRA T3010 Schedule 3 compensation (2023). National scope. Numeric column names are CRA line codes; renamed in stg_external.';