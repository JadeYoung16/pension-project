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


-- -----------------------------------------------------------------------------
-- Table 2: member_census  ←  ONCAP001_MEMBER_CENSUS_YYYYMMDD.DAT
-- -----------------------------------------------------------------------------
-- Fixed-width file (400 bytes/record), ISO-8859-1 encoded, CRLF line ending.
-- Layout defined in upstream_simulators/config/record_layouts/member_census_layout.yaml.
-- Loader handles:
--   * Stripping pad characters (' ' for char fields, '0' for num fields)
--   * Parsing YYYYMMDD strings into DATE
--   * Applying implicit_decimals=2 to numeric fields (divide by 100)
-- HDR/TRL records go to a separate control table (defined later).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.member_census (
    member_id                       TEXT,
    sin_last_4                      TEXT,
    first_name                      TEXT,
    middle_initial                  TEXT,
    last_name                       TEXT,
    dob                             DATE,
    sex_code                        TEXT,
    marital_status_code             TEXT,
    language_preference             TEXT,
    street_address                  TEXT,
    city                            TEXT,
    province                        TEXT,
    postal_code                     TEXT,
    phone                           TEXT,
    email                           TEXT,
    employer_id                     TEXT,
    hire_date                       DATE,
    enrollment_date                 DATE,
    termination_date                DATE,
    status_code                     TEXT,
    employment_type                 TEXT,
    annual_salary                   NUMERIC(12, 2),
    salary_band_code                TEXT,
    job_category                    TEXT,
    credited_service_years          NUMERIC(7, 2),
    eligible_buyback_service        NUMERIC(7, 2),
    last_buyback_leave_end_date     DATE,
    normal_retirement_date          DATE,
    accrued_annual_pension          NUMERIC(12, 2),
    beneficiary_on_file             TEXT,
    member_since_date               DATE,
    last_statement_date             DATE,
    record_status                   TEXT,
    -- audit columns
    _source_file                    TEXT        NOT NULL,
    _row_num                        BIGINT      NOT NULL,
    _loaded_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- -----------------------------------------------------------------------------
-- Table 3: member_census_control  ←  HDR + TRL records from the same .DAT file
-- -----------------------------------------------------------------------------
-- HDR (header) and TRL (trailer) records carry file-level metadata and
-- reconciliation info (record counts, salary sums, checksums).
-- Stored in one table with record_kind = 'HDR' | 'TRL' to distinguish.
-- Naming exception: source field is RECORD_TYPE; we use `record_kind` here
-- to avoid clashing with the same-named field in detail records. 
-- Most queries will GROUP BY _source_file to compare HDR.record_count vs
-- actual count of detail rows in member_census — that's the dbt test we'll
-- write in Week 4.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.member_census_control (
    record_kind                 TEXT,           -- 'HDR' or 'TRL'(Renamed from source RECORD_TYPE as we have the same column name in member_census.record_type)
    plan_code                   TEXT,           -- HDR only
    as_of_date                  DATE,           -- both
    record_count                INTEGER,        -- HDR.RECORD_COUNT or TRL.TOTAL_RECORD_COUNT
    create_timestamp            TIMESTAMP,      -- HDR only
    layout_version              TEXT,           -- HDR only
    system_id                   TEXT,           -- HDR only
    -- TRL-only fields (member status counts)
    active_count                INTEGER,
    deferred_count              INTEGER,
    retired_count               INTEGER,
    terminated_count            INTEGER,
    survivor_count              INTEGER,
    -- TRL-only reconciliation totals
    sum_annual_salary           NUMERIC(18, 2),
    sum_accrued_pension         NUMERIC(18, 2),
    checksum                    TEXT,
    -- audit
    _source_file                TEXT        NOT NULL,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()  -- we don't use it with time zone as the raw data doesn't have time zone
);