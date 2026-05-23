-- =============================================================================
-- stg_oncap__member_census
-- =============================================================================
-- One row per pension plan member (latest monthly snapshot).
-- 50,000 rows (raw has 2 monthly snapshots × 50,000 each; staging takes
-- only the latest for use as a dimension table; historical snapshots
-- remain in raw for future SCD Type 2 modeling).
--
-- 1:1 mirror of latest snapshot with:
--   - lowercase normalization on enum text columns (A/B/C principle)
--   - sex_code mapped from Statistics Canada code (1/2/9) to readable labels
--   - empty-string → NULL normalization
--   - preserve cryptic codes (status/employment_type/salary_band etc.) as-is;
--     code→label translation deferred to dim_member mart
--   - PII columns flagged in _properties.yml `meta:` for downstream
--     access-control identification
--
-- ---------------------------------------------------------------------------
-- Grain note:
--   raw_oncap.member_census has 100,000 rows = 50,000 members × 2 snapshots
--   (20231231, 20240131). Furthermore, member_id is employer-scoped, not
--   globally unique — different employers may reuse the same local member_id.
--   The true grain in raw is (member_id, employer_id, snapshot_date).
--   This staging takes latest snapshot only; PK is (member_id, employer_id).
--   SCD Type 2 modeling of changes-over-time is a Week 7+ snapshot layer
--   concern, not staging's job.
--
-- NULL semantics:
--   member_since_date         NULL = pending enrollment / migration edge
--   termination_date          NULL = currently employed (not terminated)
--   middle_initial            NULL = no middle name
--   last_buyback_leave_end    NULL = never bought back leave
--   phone / email             NULL = not provided
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'member_census') }}

),

latest_snapshot as (

    select *
    from source
    where _source_file = (
        -- Latest snapshot file by name (e.g. _20240131 > _20231231 lexicographically)
        select max(_source_file) from source
    )

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        -- Composite PK: (member_id, employer_id). member_id alone is not
        -- globally unique — see grain note in header.
        member_id,
        employer_id,                                                 -- FK

        -- --- PII: identity (preserved; flagged in yaml meta) ---------------
        sin_last_4,
        first_name,
        nullif(middle_initial, '')   as middle_initial,
        last_name,
        dob                          as date_of_birth,

        -- --- demographics (sex code mapped; others lowered) ----------------
        case sex_code
            when '1' then 'male'
            when '2' then 'female'
            when '9' then 'not_stated'
        end                          as sex,
        lower(marital_status_code)   as marital_status_code,
        lower(language_preference)   as language_preference,

        -- --- PII: contact (preserved; flagged in yaml meta) ----------------
        street_address,
        city,
        province,
        postal_code,
        nullif(phone, '')            as phone,
        nullif(email, '')            as email,

        -- --- employment ----------------------------------------------------
        hire_date,
        enrollment_date,
        termination_date,
        lower(status_code)           as status_code,
        lower(employment_type)       as employment_type,

        -- --- compensation --------------------------------------------------
        annual_salary,
        lower(salary_band_code)      as salary_band_code,
        lower(job_category)          as job_category,

        -- --- pension service & accrual -------------------------------------
        credited_service_years,
        eligible_buyback_service,
        last_buyback_leave_end_date,
        normal_retirement_date,
        accrued_annual_pension,
        beneficiary_on_file,

        -- --- membership lifecycle ------------------------------------------
        member_since_date,
        last_statement_date,
        lower(record_status)         as record_status,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from latest_snapshot

)

select * from renamed