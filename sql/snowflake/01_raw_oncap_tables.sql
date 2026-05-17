-- =============================================================================
-- raw_oncap — landing tables (Snowflake)
-- =============================================================================
-- Translated from sql/01_raw_oncap_tables.sql (Postgres).
-- Conventions preserved:
--   * One table per source file type, 1:1 mirror
--   * Audit triplet: _source_file / _row_num / _loaded_at
--   * No PKs / NOT NULL on data columns (raw is faithful, deferred to stg)
-- Run as PENSION_DEVELOPER. Set context first:
--   USE ROLE PENSION_DEVELOPER;
--   USE WAREHOUSE PENSION_WH;
--   USE DATABASE PENSION_DEV;
-- =============================================================================

USE SCHEMA RAW_ONCAP;

-- -----------------------------------------------------------------------------
-- Table 1: employer_registry
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employer_registry (
    employer_id                      STRING,
    business_number                  STRING,
    legal_name                       STRING,
    operating_name                   STRING,
    sector_category_code             STRING,
    city                             STRING,
    postal_code                      STRING,
    employer_size_band               STRING,
    employee_count                   INTEGER,
    enrolled_member_count            INTEGER,
    pay_frequency                    STRING,
    participation_start_date         DATE,
    plan_administrator_name          STRING,
    plan_administrator_email         STRING,
    status                           STRING,
    acquisition_channel              STRING,
    prospect_source                  STRING,
    first_contact_date               DATE,
    _source_file                     STRING       NOT NULL,
    _row_num                         BIGINT       NOT NULL,
    _loaded_at                       TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 2: member_census  (fixed-width source)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member_census (
    member_id                       STRING,
    sin_last_4                      STRING,
    first_name                      STRING,
    middle_initial                  STRING,
    last_name                       STRING,
    dob                             DATE,
    sex_code                        STRING,
    marital_status_code             STRING,
    language_preference             STRING,
    street_address                  STRING,
    city                            STRING,
    province                        STRING,
    postal_code                     STRING,
    phone                           STRING,
    email                           STRING,
    employer_id                     STRING,
    hire_date                       DATE,
    enrollment_date                 DATE,
    termination_date                DATE,
    status_code                     STRING,
    employment_type                 STRING,
    annual_salary                   NUMBER(12, 2),
    salary_band_code                STRING,
    job_category                    STRING,
    credited_service_years          NUMBER(7, 2),
    eligible_buyback_service        NUMBER(7, 2),
    last_buyback_leave_end_date     DATE,
    normal_retirement_date          DATE,
    accrued_annual_pension          NUMBER(12, 2),
    beneficiary_on_file             STRING,
    member_since_date               DATE,
    last_statement_date             DATE,
    record_status                   STRING,
    _source_file                    STRING       NOT NULL,
    _row_num                        BIGINT       NOT NULL,
    _loaded_at                      TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 3: member_census_control  (HDR + TRL from .DAT)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member_census_control (
    record_kind                 STRING,
    plan_code                   STRING,
    as_of_date                  DATE,
    record_count                INTEGER,
    create_timestamp            TIMESTAMP_NTZ,   -- no TZ in source
    layout_version              STRING,
    system_id                   STRING,
    active_count                INTEGER,
    deferred_count              INTEGER,
    retired_count               INTEGER,
    terminated_count            INTEGER,
    survivor_count              INTEGER,
    sum_annual_salary           NUMBER(18, 2),
    sum_accrued_pension         NUMBER(18, 2),
    checksum                    STRING,
    _source_file                STRING       NOT NULL,
    _loaded_at                  TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 4: transaction  (pipe-delimited)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction (
    transaction_id              STRING,
    member_id                   STRING,
    employer_id                 STRING,
    pay_date                    DATE,
    pay_period_start            DATE,
    pay_period_end              DATE,
    pay_frequency_code          STRING,
    pensionable_earnings        NUMBER(12, 2),
    member_contribution         NUMBER(12, 2),
    employer_contribution       NUMBER(12, 2),
    contribution_type           STRING,
    buyback_reference_id        STRING,
    transaction_status          STRING,
    _source_file                STRING       NOT NULL,
    _row_num                    BIGINT       NOT NULL,
    _loaded_at                  TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 5: transaction_control  (H + T from .TXT)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction_control (
    record_kind                 STRING,
    plan_code                   STRING,
    file_type                   STRING,
    pay_date                    DATE,
    record_count                INTEGER,
    create_timestamp            TIMESTAMP_TZ,
    sum_member_contribution     NUMBER(18, 2),
    sum_employer_contribution   NUMBER(18, 2),
    _source_file                STRING       NOT NULL,
    _loaded_at                  TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 6: life_event  (pipe-delimited, polymorphic)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS life_event (
    event_id                         STRING,
    member_id                        STRING,
    employer_id                      STRING,
    event_type_code                  STRING,
    event_date                       DATE,
    event_timestamp                  TIMESTAMP_TZ,
    buyback_category_code            STRING,
    buyback_service_years            NUMBER(7, 2),
    leave_end_date                   DATE,
    months_since_eligibility         INTEGER,
    is_within_window                 STRING,
    is_open_option                   STRING,
    member_cost                      NUMBER(12, 2),
    employer_cost                    NUMBER(12, 2),
    total_cost                       NUMBER(12, 2),
    payment_method                   STRING,
    installment_months               INTEGER,
    event_status                     STRING,
    channel_code                     STRING,
    notes                            STRING,
    _source_file                     STRING       NOT NULL,
    _row_num                         BIGINT       NOT NULL,
    _loaded_at                       TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 7: portal_event  (JSONL → hybrid scalar + VARIANT)
-- -----------------------------------------------------------------------------
-- event_properties was JSONB in Postgres; VARIANT in Snowflake.
-- VARIANT is the native semi-structured type, queryable via dot-notation:
--   SELECT event_properties:click_target::STRING FROM portal_event
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_event (
    event_id                    STRING,
    member_id                   STRING,
    event_timestamp             TIMESTAMP_TZ,
    event_type                  STRING,
    session_id                  STRING,
    ip_hash                     STRING,
    user_agent                  STRING,
    page_path                   STRING,
    referrer                    STRING,
    event_properties            VARIANT,
    _source_file                STRING       NOT NULL,
    _row_num                    BIGINT       NOT NULL,
    _loaded_at                  TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 8: call_log
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS call_log (
    call_id                          STRING,
    member_id                        STRING,
    call_timestamp                   TIMESTAMP_TZ,
    duration_seconds                 INTEGER,
    call_reason_category             STRING,
    call_reason_subcategory          STRING,
    resolution_code                  STRING,
    agent_id                         STRING,
    csat_score                       INTEGER,
    notes                            STRING,
    _source_file                     STRING       NOT NULL,
    _row_num                         BIGINT       NOT NULL,
    _loaded_at                       TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 9: seminar_attendance
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seminar_attendance (
    attendance_id                    STRING,
    member_id                        STRING,
    seminar_date                     DATE,
    seminar_location                 STRING,
    seminar_topic                    STRING,
    attendance_format                STRING,
    registration_date                DATE,
    attended_flag                    STRING,
    _source_file                     STRING       NOT NULL,
    _row_num                         BIGINT       NOT NULL,
    _loaded_at                       TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Table 10: email_engagement
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_engagement (
    event_id                         STRING,
    member_id                        STRING,
    campaign_id                      STRING,
    campaign_name                    STRING,
    event_type                       STRING,
    event_timestamp                  TIMESTAMP_TZ,
    link_url_clicked                 STRING,
    _source_file                     STRING       NOT NULL,
    _row_num                         BIGINT       NOT NULL,
    _loaded_at                       TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Meta: _rejected
-- -----------------------------------------------------------------------------
-- Quarantine for malformed rows. In Snowflake the equivalent path is
-- COPY INTO ... ON_ERROR = CONTINUE; we will route those errors here from
-- a wrapper script in Day 5 (TBD design point).
-- Indexes dropped — Snowflake uses micro-partitions; for our volume (likely
-- <1k rejected rows total) no clustering needed.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _rejected (
    rejected_id     BIGINT       AUTOINCREMENT START 1 INCREMENT 1 PRIMARY KEY,
    target_table    STRING       NOT NULL,
    source_file     STRING       NOT NULL,
    row_num         BIGINT       NOT NULL,
    raw_line        STRING       NOT NULL,
    failure_reason  STRING       NOT NULL,
    failure_detail  STRING,
    rejected_at     TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Meta: _load_audit
-- -----------------------------------------------------------------------------
-- One row per data-load operation. In Snowflake the equivalent will be
-- "one row per COPY INTO invocation" (Day 5 design).
--
-- Note: Postgres CHECK constraint dropped (Snowflake doesn't support CHECK).
-- status convention enforced in code: must be 'success' or 'failed'.
-- source_files is VARIANT (was JSONB) — query via [0]:name::STRING etc.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _load_audit (
    load_id            BIGINT       AUTOINCREMENT START 1 INCREMENT 1 PRIMARY KEY,
    target_table       STRING       NOT NULL,
    started_at         TIMESTAMP_TZ NOT NULL,
    finished_at        TIMESTAMP_TZ NOT NULL,
    status             STRING       NOT NULL,   -- 'success' | 'failed'
    files_loaded       INTEGER      NOT NULL,
    rows_good          BIGINT       NOT NULL,
    rows_rejected      BIGINT       NOT NULL,
    source_files       VARIANT      NOT NULL,
    failure_reason     STRING,
    _created_at        TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'One row per loader/COPY INTO invocation. Logs status, row counts, per-file detail.';