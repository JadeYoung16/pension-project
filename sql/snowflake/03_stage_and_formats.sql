-- =============================================================================
-- Snowflake: external stage + file formats for RAW_ONCAP / RAW_EXTERNAL loading
-- =============================================================================
-- ELT path: local extracts -> ADLS Gen2 (landing) -> LANDING_STAGE -> COPY INTO.
-- Replaces the Week 4 internal stage (@LOAD_STAGE + PUT): files are now landed
-- by loaders/azure/upload_to_adls.py, and Snowflake reads them in place through
-- the AZURE_LANDING_INT storage integration (03a_azure_storage_integration.sql).
--
-- Stage layout mirrors the landing zone:
--   @LANDING_STAGE/<source_system>/<dataset>/<file>
--   e.g. @LANDING_STAGE/esp/email_engagement/ONCAP001_EMAIL_ENGAGEMENT_202309.csv
-- =============================================================================

USE ROLE PENSION_DEVELOPER;
USE WAREHOUSE PENSION_WH;
USE DATABASE PENSION_DEV;
USE SCHEMA RAW_ONCAP;

-- -----------------------------------------------------------------------------
-- External stage over the ADLS Gen2 landing container
-- -----------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS LANDING_STAGE
  URL = 'azure://oncaplandingjy26.blob.core.windows.net/landing/'
  STORAGE_INTEGRATION = AZURE_LANDING_INT
  COMMENT = 'External stage over ADLS Gen2 landing/. Read-only via AZURE_LANDING_INT.';

-- -----------------------------------------------------------------------------
-- File format 1: CSV_FORMAT — positional CSV with a header line to skip
-- -----------------------------------------------------------------------------
-- Used by: employer_registry, call_log, seminar_attendance, salary_history,
--          t3010_ident, t3010_schedule3, member_census (after preprocess),
--          campaign_assignment
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT CSV_FORMAT
  TYPE = CSV
  FIELD_DELIMITER = ','
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL', '\\N')
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE                     -- preserve significant whitespace in raw layer
  ENCODING = 'UTF8'
  COMMENT = 'Standard CSV: comma-delimited, double-quoted, header line skipped, UTF-8';

-- -----------------------------------------------------------------------------
-- File format 2: CSV_HEADER_FORMAT — CSV matched BY COLUMN NAME
-- -----------------------------------------------------------------------------
-- Used by: email_engagement. The ESP changed its export on 2023-09-15 (added
-- bounce_type, reordered columns). Positional $1..$n mapping would silently
-- load values into the wrong columns; PARSE_HEADER + MATCH_BY_COLUMN_NAME
-- maps by header name, and columns absent from older files load as NULL.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT CSV_HEADER_FORMAT
  TYPE = CSV
  FIELD_DELIMITER = ','
  PARSE_HEADER = TRUE                    -- header row supplies column names (SKIP_HEADER must be 0)
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE -- file has 7-8 cols, table 11 (+ audit cols); mapping is by name
                                         -- trade-off: a NEW vendor column absent from the table is ignored
                                         -- silently -> guard with a header check in staging
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL', '\\N')
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE
  ENCODING = 'UTF8'
  COMMENT = 'CSV loaded by column name (schema-drift tolerant). Use with MATCH_BY_COLUMN_NAME.';

-- -----------------------------------------------------------------------------
-- File format 3: PIPE_FORMAT — pipe-delimited (transactions, life_events)
-- -----------------------------------------------------------------------------
-- transactions: H row + column header -> SKIP_HEADER = 2 (set per COPY)
-- life_events:  column header only    -> SKIP_HEADER = 1 (set per COPY)
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
  COMMENT = 'Pipe-delimited. SKIP_HEADER overridden per COPY (transaction=2, life_event=1).';

-- -----------------------------------------------------------------------------
-- File format 4: JSON_FORMAT — portal_event JSONL
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT JSON_FORMAT
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE              -- JSONL is one object per line, not an array
  ALLOW_DUPLICATE = FALSE
  STRIP_NULL_VALUES = FALSE              -- preserve null fields in raw
  COMMENT = 'JSONL (one JSON object per line). Extraction via SELECT in COPY INTO.';

-- -----------------------------------------------------------------------------
-- File format 5: JSONL_LINE_FORMAT — each JSONL line as one raw text field
-- -----------------------------------------------------------------------------
-- Used by: portal_event. With TYPE = JSON, ON_ERROR = CONTINUE skips a WHOLE
-- FILE when one line is malformed (a day of events lost). Reading each line
-- as text and parsing with TRY_PARSE_JSON in the COPY keeps every good row
-- and quarantines only the bad line (kept verbatim in _raw_line).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT JSONL_LINE_FORMAT
  TYPE = CSV
  FIELD_DELIMITER = NONE                 -- whole line is one field
  RECORD_DELIMITER = '\n'
  FIELD_OPTIONALLY_ENCLOSED_BY = NONE
  ESCAPE_UNENCLOSED_FIELD = NONE         -- keep backslashes inside JSON untouched
  SKIP_HEADER = 0
  NULL_IF = ()
  EMPTY_FIELD_AS_NULL = FALSE
  ENCODING = 'UTF8'
  COMMENT = 'One JSONL line per row as raw text; parse with TRY_PARSE_JSON in COPY.';

-- -----------------------------------------------------------------------------
-- Verify: Snowflake can see the landed files through the integration
-- -----------------------------------------------------------------------------
LIST @LANDING_STAGE/crm/campaign_assignment/;

SELECT $1, $2, $3, $4
FROM @LANDING_STAGE/crm/campaign_assignment/ (FILE_FORMAT => 'CSV_FORMAT')
LIMIT 5;