-- =============================================================================
-- Snowflake: stage + file formats for RAW_ONCAP / RAW_EXTERNAL loading
-- =============================================================================
-- Day 5 of Week 4. One internal stage shared across both schemas (table
-- separation via subdirectory prefix). Three file format objects cover
-- our 3 native source formats; fixed-width member_census is preprocessed
-- to CSV locally and uses CSV_FORMAT (see loaders/snowflake/preprocess.py
-- in Day 5).
-- =============================================================================

USE ROLE PENSION_DEVELOPER;
USE WAREHOUSE PENSION_WH;
USE DATABASE PENSION_DEV;

-- -----------------------------------------------------------------------------
-- Stage: internal named stage in raw_oncap
-- -----------------------------------------------------------------------------
-- File layout convention:
--   @LOAD_STAGE/<table_name>/<source_filename>
-- e.g. @LOAD_STAGE/employer_registry/ONCAP001_EMPLOYER_REGISTRY_20240131.csv
--      @LOAD_STAGE/t3010_ident/ident_2023_update.csv
--      @LOAD_STAGE/member_census/ONCAP001_MEMBER_CENSUS_20240131.csv  ← preprocessed
-- -----------------------------------------------------------------------------
USE SCHEMA RAW_ONCAP;

CREATE STAGE IF NOT EXISTS LOAD_STAGE
  COMMENT = 'Shared internal stage for all raw_oncap + raw_external loading. Files organized by <table_name>/ subdirectory.';

-- -----------------------------------------------------------------------------
-- File format 1: CSV_FORMAT — for comma-delimited CSVs
-- -----------------------------------------------------------------------------
-- Used by: employer_registry, call_log, seminar_attendance, email_engagement,
--          t3010_ident, t3010_schedule3, member_census (after preprocess)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT CSV_FORMAT
  TYPE = CSV
  FIELD_DELIMITER = ','
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL', '\\N')          -- '\\N' matches Postgres COPY NULL convention
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE                     -- preserve significant whitespace in raw layer
  ENCODING = 'UTF8'
  COMMENT = 'Standard CSV: comma-delimited, double-quoted, header line, UTF-8';

-- -----------------------------------------------------------------------------
-- File format 2: PIPE_FORMAT — for pipe-delimited files (transactions, life_events)
-- -----------------------------------------------------------------------------
-- transactions have H + column-header + detail + T  → SKIP_HEADER = 2
-- life_events have only column-header + detail      → SKIP_HEADER = 1
-- We default to SKIP_HEADER = 0 here and override per-COPY-INTO; see Day 5 plan.
-- Also: H/T rows in transactions need separate handling (load to control table);
-- defer that to Day 5 design discussion (option: pre-filter in Python, or
-- COPY twice with PATTERN, or post-INSERT split).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT PIPE_FORMAT
  TYPE = CSV
  FIELD_DELIMITER = '|'
  SKIP_HEADER = 0                        -- override per COPY
  FIELD_OPTIONALLY_ENCLOSED_BY = NONE
  NULL_IF = ('', 'NULL', '\\N')
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE
  ENCODING = 'UTF8'
  COMMENT = 'Pipe-delimited (CSV type with | delimiter). SKIP_HEADER overridden per COPY because transaction files have H+header (2) while life_events have header only (1).';

-- -----------------------------------------------------------------------------
-- File format 3: JSON_FORMAT — for portal_event JSONL
-- -----------------------------------------------------------------------------
-- JSONL = one JSON object per line. Snowflake TYPE=JSON treats it as
-- semi-structured; we'll COPY INTO with explicit column extraction via
-- a SELECT, since portal_event has scalar columns + a VARIANT event_properties.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT JSON_FORMAT
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE              -- JSONL is one-object-per-line, not array
  ALLOW_DUPLICATE = FALSE
  STRIP_NULL_VALUES = FALSE              -- preserve null fields in raw
  COMMENT = 'JSONL (one JSON object per line). Extraction via SELECT in COPY INTO transformation.';

-- -----------------------------------------------------------------------------
-- Verify
-- -----------------------------------------------------------------------------
SHOW STAGES IN SCHEMA RAW_ONCAP;
SHOW FILE FORMATS IN SCHEMA RAW_ONCAP;