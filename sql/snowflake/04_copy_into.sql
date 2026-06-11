-- =============================================================================
-- Snowflake: COPY INTO — load staged files into RAW_ONCAP / RAW_EXTERNAL tables
-- =============================================================================
-- Week 7 (Airflow): scripted from the Day-5 Snowsight worksheet that was never
-- committed. Runs AFTER put_files.py has PUT source files into @LOAD_STAGE.
-- Depends on objects from 03_stage_and_formats.sql (stage + CSV/PIPE/JSON formats).
--
-- Per-table specifics preserved verbatim from the validated Day-5 version:
--   - transaction : PIPE_FORMAT, SKIP_HEADER = 2  (H-row + column header)
--   - life_event  : PIPE_FORMAT, SKIP_HEADER = 1  (column header only)
--   - portal_event: JSON_FORMAT, VARIANT extraction via $1:field::type
--   - all others  : CSV_FORMAT  (SKIP_HEADER = 1 from the format object)
-- All COPYs use ON_ERROR = CONTINUE (row-level reject for CSV/PIPE;
--   file-level for JSON — portal_event under-loads by design, see Day-5 notes).
-- _source_file / _row_num audit columns come from METADATA$FILENAME /
--   METADATA$FILE_ROW_NUMBER.
-- =============================================================================

USE ROLE PENSION_DEVELOPER;
USE WAREHOUSE PENSION_WH;
USE DATABASE PENSION_DEV;
USE SCHEMA RAW_ONCAP;


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
        METADATA$FILENAME,           -- _source_file
        METADATA$FILE_ROW_NUMBER     -- _row_num
    FROM @LOAD_STAGE/employer_registry/
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
    FROM @LOAD_STAGE/life_event/
)
FILE_FORMAT = (FORMAT_NAME = PIPE_FORMAT, SKIP_HEADER = 1)
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
    FROM @LOAD_STAGE/member_census/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO portal_event (
    event_id, member_id, event_timestamp, event_type,
    session_id, ip_hash, user_agent, page_path, referrer,
    event_properties,
    _source_file, _row_num
)
FROM (
    SELECT
        $1:event_id::STRING,
        $1:member_id::STRING,
        $1:event_timestamp::TIMESTAMP_TZ,
        $1:event_type::STRING,
        $1:session_id::STRING,
        $1:ip_hash::STRING,
        $1:user_agent::STRING,
        $1:page_path::STRING,
        $1:referrer::STRING,
        $1:event_properties,
        METADATA$FILENAME,
        METADATA$FILE_ROW_NUMBER
    FROM @LOAD_STAGE/portal_event/
)
FILE_FORMAT = (FORMAT_NAME = JSON_FORMAT)
ON_ERROR = CONTINUE;


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
    FROM @LOAD_STAGE/transaction/
)
FILE_FORMAT = (FORMAT_NAME = PIPE_FORMAT, SKIP_HEADER = 2)
ON_ERROR = CONTINUE;


COPY INTO email_engagement (
    event_id, member_id, campaign_id, campaign_name,
    event_type, event_timestamp, link_url_clicked,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @LOAD_STAGE/email_engagement/
)
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
    FROM @LOAD_STAGE/seminar_attendance/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


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
    FROM @LOAD_STAGE/call_log/
)
FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)
ON_ERROR = CONTINUE;


COPY INTO RAW_EXTERNAL.t3010_ident (
    bn, category, sub_category, designation, legal_name, account_name,
    address_line_1, address_line_2, city, province, postal_code, country,
    _source_file, _row_num
)
FROM (
    SELECT
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
        METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @PENSION_DEV.RAW_ONCAP.LOAD_STAGE/t3010_ident/
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
    FROM @PENSION_DEV.RAW_ONCAP.LOAD_STAGE/t3010_schedule3/
)
FILE_FORMAT = (FORMAT_NAME = PENSION_DEV.RAW_ONCAP.CSV_FORMAT)
ON_ERROR = CONTINUE;