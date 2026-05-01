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


-- -----------------------------------------------------------------------------
-- Table 4: transaction  ←  ONCAP001_TXN_PAYDATE_YYYYMMDD.TXT
-- -----------------------------------------------------------------------------
-- Pipe-delimited text, UTF-8.  File structure:
--   Line 1:        H|ONCAP001|TXN|<pay_date>|<record_count>|<create_ts>
--   Line 2:        column header row (skipped by loader)
--   Lines 3..N-1:  detail records (loaded into this table)
--   Line N:        T|ONCAP001|<record_count>|<sum_mbr>|<sum_emp>
--
-- Money columns use NUMERIC(12, 2), matching annual_salary precision in
-- member_census for cross-table consistency.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.transaction (
    transaction_id              TEXT,
    member_id                   TEXT,
    employer_id                 TEXT,
    pay_date                    DATE,
    pay_period_start            DATE,
    pay_period_end              DATE,
    pay_frequency_code          TEXT,
    pensionable_earnings        NUMERIC(12, 2),
    member_contribution         NUMERIC(12, 2),
    employer_contribution       NUMERIC(12, 2),
    contribution_type           TEXT,
    buyback_reference_id        TEXT,
    transaction_status          TEXT,
    -- audit
    _source_file                TEXT        NOT NULL,
    _row_num                    BIGINT      NOT NULL,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- -----------------------------------------------------------------------------
-- Table 5: transaction_control  ←  H + T records from the same .TXT file
-- -----------------------------------------------------------------------------
-- Header (H) and trailer (T) records carry file-level metadata + reconciliation
-- totals.  One row each per source file — small volume.
--
-- Naming exception: source field is "record_type" (the leading H or T);
-- we use `record_kind` here to stay consistent with member_census_control.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.transaction_control (
    record_kind                 TEXT,           -- 'H' or 'T'
    plan_code                   TEXT,           -- both
    file_type                   TEXT,           -- H only ('TXN')
    pay_date                    DATE,           -- H only
    record_count                INTEGER,        -- both (H declares, T confirms)
    create_timestamp            TIMESTAMPTZ,    -- H only; ISO 8601 with TZ in source, so TIMESTAMPTZ
    sum_member_contribution     NUMERIC(18, 2), -- T only
    sum_employer_contribution   NUMERIC(18, 2), -- T only
    -- audit
    _source_file                TEXT        NOT NULL,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- -----------------------------------------------------------------------------
-- Table 6: life_event  ←  ONCAP001_LIFE_EVENTS_YYYYMM.TXT (or similar)
-- -----------------------------------------------------------------------------
-- Pipe-delimited, UTF-8.  Polymorphic events — different event_type_code
-- values use different subsets of fields, so most non-key columns are
-- nullable in raw.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.life_event (
    event_id                         TEXT,
    member_id                        TEXT,
    employer_id                      TEXT,
    event_type_code                  TEXT,
    event_date                       DATE,
    event_timestamp                  TIMESTAMPTZ,
    buyback_category_code            TEXT,
    buyback_service_years            NUMERIC(7,2),
    leave_end_date                   DATE,
    months_since_eligibility         INTEGER,
    is_within_window                 TEXT,
    is_open_option                   TEXT,
    member_cost                      NUMERIC(12,2),
    employer_cost                    NUMERIC(12,2),
    total_cost                       NUMERIC(12,2),
    payment_method                   TEXT,
    installment_months               INTEGER,
    event_status                     TEXT,
    channel_code                     TEXT,
    notes                            TEXT,
    -- audit line 
    _source_file                     TEXT   NOT NULL,
    _row_num                         BIGINT NOT NULL,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- -----------------------------------------------------------------------------
-- Table 7: portal_event  ←  ONCAP001_PORTAL_EVENTS_YYYYMMDD.jsonl
-- -----------------------------------------------------------------------------
-- JSONL format (one JSON object per line), UTF-8.  Approximately 90 daily
-- files covering the observation window.
--
-- Hybrid typing: scalar top-level fields are unpacked into typed columns for
-- easy querying; the nested `event_properties` object stays as JSONB because
-- its shape varies by event_type.  This mirrors how Fivetran/Airbyte and
-- modern warehouses (Snowflake VARIANT, BigQuery STRUCT) handle event data.
--
-- The loader will also handle ~1-in-10k malformed JSON lines (per spec) by
-- routing them to raw_oncap._rejected (Week 3 loader task).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.portal_event (
    event_id                    TEXT,
    member_id                   TEXT,
    event_timestamp             TIMESTAMPTZ,
    event_type                  TEXT,
    session_id                  TEXT,
    ip_hash                     TEXT,
    user_agent                  TEXT,
    page_path                   TEXT,
    referrer                    TEXT,
    event_properties            JSONB,
    -- audit
    _source_file                TEXT        NOT NULL,
    _row_num                    BIGINT      NOT NULL,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);



-- -----------------------------------------------------------------------------
-- Table 8: call_log  ←  ONCAP001_CALL_LOG_YYYYMM.csv
-- -----------------------------------------------------------------------------
-- CSV format.  2023-11 to 2024-01
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_oncap.call_log (
    call_id                          TEXT,
    member_id                        TEXT,
    call_timestamp                   TIMESTAMPTZ,
    duration_seconds                 INTEGER,
    call_reason_category             TEXT,
    call_reason_subcategory          TEXT,
    resolution_code                  TEXT,
    agent_id                         TEXT,
    csat_score                       INTEGER,
    notes                            TEXT,
    -- audit
    _source_file                     TEXT NOT NULL,
    _row_num                         BIGINT NOT NULL,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()

);


-- -----------------------------------------------------------------------------
-- Table 9: seminar_attendance  ←  ONCAP001_SEMINAR_ATTENDANCE_YYYY.csv
-- -----------------------------------------------------------------------------
-- CSV format.  2022 and 2023
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_oncap.seminar_attendance (
    attendance_id                    TEXT,
    member_id                        TEXT,
    seminar_date                     DATE,
    seminar_location                 TEXT,
    seminar_topic                    TEXT,
    attendance_format                TEXT,
    registration_date                DATE,
    attended_flag                    TEXT,
    -- audit
    _source_file                     TEXT NOT NULL,
    _row_num                         BIGINT NOT NULL,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- Table 10: email_engagement  ←  ONCAP001_EMAIL_ENGAGEMENT_YYYYMM.csv
-- -----------------------------------------------------------------------------
-- CSV format.  2023-NOV to 2024-JAN
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_oncap.email_engagement (
    event_id                         TEXT,
    member_id                        TEXT,
    campaign_id                      TEXT,
    campaign_name                    TEXT,
    event_type                       TEXT,
    event_timestamp                  TIMESTAMPTZ,
    link_url_clicked                 TEXT,
    -- audit
    _source_file                     TEXT NOT NULL,
    _row_num                         BIGINT NOT NULL,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()

);




-- -----------------------------------------------------------------------------
-- Table 10: _rejected  ←  raw_oncap._rejected
-- -----------------------------------------------------------------------------
-- Quarantine table for rows that fail to parse during loading.
-- Loader writes here instead of raising; the run continues.
-- -----------------------------------------------------------------------------


CREATE TABLE raw_oncap._rejected (
    rejected_id     BIGSERIAL PRIMARY KEY,
    target_table    TEXT        NOT NULL,
    source_file     TEXT        NOT NULL,
    row_num         BIGINT      NOT NULL,
    raw_line        TEXT        NOT NULL,
    failure_reason  TEXT        NOT NULL,
    failure_detail  TEXT,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rejected_target_table ON raw_oncap._rejected (target_table);
CREATE INDEX idx_rejected_rejected_at  ON raw_oncap._rejected (rejected_at);