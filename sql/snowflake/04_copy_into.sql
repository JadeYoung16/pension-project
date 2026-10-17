-- =============================================================================
-- Snowflake: COPY INTO — load landed files into RAW_ONCAP / RAW_EXTERNAL
-- =============================================================================
-- Source: @LANDING_STAGE (external stage over ADLS Gen2 landing/, see 03_*.sql)
--   path = <source_system>/<dataset>/   (mirrors loaders/azure/upload_to_adls.py)
--
-- Idempotency: every table is TRUNCATEd once before its COPY(s). TRUNCATE also
-- clears Snowflake load metadata, so a re-run reloads the full set instead of
-- skipping "already loaded" files — and no file is ever loaded twice.
--
-- Per-table specifics:
--   transaction        PIPE_FORMAT, SKIP_HEADER = 2 (H row + column header)
--   life_event         PIPE_FORMAT, SKIP_HEADER = 1
--   email_engagement   CSV_HEADER_FORMAT + MATCH_BY_COLUMN_NAME: the ESP export
--                      changed on 2023-09-15 (bounce_type added, columns
--                      reordered). Loading by name, not position, keeps every
--                      value in the right column. bounce_type is NULL before.
--   campaign_assignment  two COPYs into one table: v1 (CRM export) and v2
--                      (Excel re-save with renamed, reordered headers) need
--                      different column mappings. Raw keeps both versions.
--   portal_event       JSONL_LINE_FORMAT + TRY_PARSE_JSON: a malformed line is
--                      kept verbatim in _raw_line instead of the whole file
--                      being skipped.
--   others             CSV_FORMAT (SKIP_HEADER = 1)
-- All COPYs use ON_ERROR = CONTINUE. Audit columns: METADATA$FILENAME /
-- METADATA$FILE_ROW_NUMBER.
--
-- Executed by loaders/snowflake/run_copy.py (splits on semicolons, so keep
-- semicolons and apostrophes out of comments).
-- =============================================================================

USE ROLE PENSION_DEVELOPER;
USE WAREHOUSE PENSION_WH;
USE DATABASE PENSION_DEV;
USE SCHEMA RAW_ONCAP;

TRUNCATE TABLE employer_registry;
TRUNCATE TABLE member_census;
TRUNCATE TABLE life_event;
TRUNCATE TABLE transaction;
TRUNCATE TABLE salary_history;
TRUNCATE TABLE email_engagement;
TRUNCATE TABLE portal_event;
TRUNCATE TABLE campaign_assignment;
TRUNCATE TABLE seminar_attendance;
TRUNCATE TABLE call_log;
TRUNCATE TABLE RAW_EXTERNAL.t3010_ident;
TRUNCATE TABLE RAW_EXTERNAL.t3010_schedule3;


-- pension_admin ---------------------------------------------------------------

COPY INTO employer_registry (
    employer_id, business_number, legal_name, operating_name,
    sector_category_code, city, postal_code, employer_size_band,
    employee_count, enrolled_member_count, pay_frequency,
    participation_start_date, plan_administrator_name, plan_administrator_email,
    status, acquisition_channel, prospect_source, first_contact_date,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
        $12, $13, $14, $15, $16, $17, $18,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/pension_admin/employer_registry/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO member_census (
    member_id, sin_last_4, first_name, middle_initial, last_name,
    dob, sex_code, marital_status_code, language_preference,
    street_address, city, province, postal_code, phone, email,
    employer_id, hire_date, enrollment_date, termination_date,
    status_code, employment_type, annual_salary, salary_band_code,
    job_category, credited_service_years, eligible_buyback_service,
    last_buyback_leave_end_date, normal_retirement_date,
    accrued_annual_pension, beneficiary_on_file, member_since_date,
    last_statement_date, record_status,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
        $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
        $31, $32, $33,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/pension_admin/member_census/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO life_event (
    event_id, member_id, employer_id, event_type_code, event_date,
    event_timestamp, buyback_category_code, buyback_service_years,
    leave_end_date, months_since_eligibility, is_within_window,
    is_open_option, member_cost, employer_cost, total_cost,
    payment_method, installment_months, event_status, channel_code, notes,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/pension_admin/life_event/
)
FILE_FORMAT = (FORMAT_NAME = PIPE_FORMAT, SKIP_HEADER = 1)
ON_ERROR = CONTINUE;


-- employer_sftp ---------------------------------------------------------------

COPY INTO transaction (
    transaction_id, member_id, employer_id, pay_date,
    pay_period_start, pay_period_end, pay_frequency_code,
    pensionable_earnings, member_contribution, employer_contribution,
    contribution_type, buyback_reference_id, transaction_status,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/employer_sftp/transaction/
)
FILE_FORMAT = (FORMAT_NAME = PIPE_FORMAT, SKIP_HEADER = 2)
ON_ERROR = CONTINUE;


COPY INTO salary_history (
    member_id, employer_id, effective_date, annual_salary,
    change_reason, reported_at,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/employer_sftp/salary_history/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


-- esp: load BY COLUMN NAME across the 2023-09 schema change -------------------

COPY INTO email_engagement
FROM @LANDING_STAGE/esp/email_engagement/
FILE_FORMAT = (FORMAT_NAME = CSV_HEADER_FORMAT)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
INCLUDE_METADATA = (
    _source_file = METADATA$FILENAME,
    _row_num     = METADATA$FILE_ROW_NUMBER,
    _loaded_at   = METADATA$START_SCAN_TIME   -- column DEFAULTs are not applied with MATCH_BY_COLUMN_NAME
)
ON_ERROR = CONTINUE;


-- web_analytics: line-level JSON parsing ---------------------------------------

COPY INTO portal_event (
    event_id, member_id, event_timestamp, event_type,
    session_id, ip_hash, user_agent, page_path, referrer,
    event_properties, _raw_line,
    _source_file, _row_num
)
FROM (
    SELECT
        TRY_PARSE_JSON($1):event_id::STRING,
        TRY_PARSE_JSON($1):member_id::STRING,
        TRY_PARSE_JSON($1):event_timestamp::TIMESTAMP_TZ,
        TRY_PARSE_JSON($1):event_type::STRING,
        TRY_PARSE_JSON($1):session_id::STRING,
        TRY_PARSE_JSON($1):ip_hash::STRING,
        TRY_PARSE_JSON($1):user_agent::STRING,
        TRY_PARSE_JSON($1):page_path::STRING,
        TRY_PARSE_JSON($1):referrer::STRING,
        TRY_PARSE_JSON($1):event_properties,
        IFF(TRY_PARSE_JSON($1) IS NULL, $1, NULL),
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/web_analytics/portal_event/
)
FILE_FORMAT = (FORMAT_NAME = JSONL_LINE_FORMAT)
ON_ERROR = CONTINUE;


-- crm: two export versions with different column orders ------------------------

COPY INTO campaign_assignment (
    member_id, campaign_id, segment, arm, assigned_date, scheduled_send_date,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/crm/campaign_assignment/
)
PATTERN = '.*_v1_.*[.]csv'
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO campaign_assignment (
    member_id, campaign_id, segment, arm, assigned_date, scheduled_send_date,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $5, $3, $2, $6, $4,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/crm/campaign_assignment/
)
PATTERN = '.*_v2_FINAL_.*[.]csv'
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO seminar_attendance (
    attendance_id, member_id, seminar_date, seminar_location,
    seminar_topic, attendance_format, registration_date, attended_flag,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/crm/seminar_attendance/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


-- contact_center --------------------------------------------------------------

COPY INTO call_log (
    call_id, member_id, call_timestamp, duration_seconds,
    call_reason_category, call_reason_subcategory, resolution_code,
    agent_id, csat_score, notes,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LANDING_STAGE/contact_center/call_log/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


-- cra_t3010 (target schema RAW_EXTERNAL, so stage and format fully qualified) ---

COPY INTO RAW_EXTERNAL.t3010_ident (
    bn, category, sub_category, designation, legal_name, account_name,
    address_line_1, address_line_2, city, province, postal_code, country,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @PENSION_DEV.RAW_ONCAP.LANDING_STAGE/cra_t3010/t3010_ident/
)
FILE_FORMAT = (FORMAT_NAME = PENSION_DEV.RAW_ONCAP.CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO RAW_EXTERNAL.t3010_schedule3 (
    bn, fpe, form_id,
    "300", "305", "310", "315", "320", "325", "330", "335",
    "340", "345", "370", "380", "390",
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3,
        $4, $5, $6, $7, $8, $9, $10, $11,
        $12, $13, $14, $15, $16,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @PENSION_DEV.RAW_ONCAP.LANDING_STAGE/cra_t3010/t3010_schedule3/
)
FILE_FORMAT = (FORMAT_NAME = PENSION_DEV.RAW_ONCAP.CSV_FORMAT)
ON_ERROR = CONTINUE;