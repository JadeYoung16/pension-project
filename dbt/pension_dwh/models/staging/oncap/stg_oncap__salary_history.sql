-- =============================================================================
-- stg_oncap__salary_history
-- =============================================================================
-- One row per salary report from the employer portal feed. 142,194 rows.
-- Grain = one reported salary record at (member_id, employer_id,
-- effective_date) level. NOT deduplicated here — duplicate reports are
-- intentional (resubmissions with differing reported_at); dedup is applied
-- downstream in the snapshot's query (qualify row_number on the natural key)
-- so the snapshot receives a unique business key.
--
-- 1:1 mirror of raw with minimal standardization:
--   - lower() on change_reason enum (consistency with stg enum convention)
--   - member_id / employer_id passed through as-is (same-source byte-aligned
--     to member_census / transaction; any reformatting would risk breaking
--     the join to dim_member)
--   - cast nothing (raw types already correct: annual_salary NUMBER(12,2),
--     effective_date DATE, reported_at TIMESTAMP_NTZ)
--
-- Known data quality issues (flagged by dbt test, see _properties.yml; NOT
-- mutated here — staging validates/standardizes/flags, it does not fix
-- business values):
--   1. annual_salary ~2.0% NULL (missing report; empty field → NULL at COPY).
--   2. annual_salary ~0.3% negative (payroll reversals, tagged CORRECTION).
--   3. annual_salary rare 10x outliers (fat-finger; multi-dirty rows may mask).
--   4. duplicate natural key (member_id, employer_id, effective_date) from
--      resubmissions — distinct on reported_at. Deduped at snapshot, not here.
--   5. reported_at later than effective_date (~4% backdated/retroactive).
--   6. ~100 orphan member_id (50001-59999) absent from member_census —
--      relationships test target.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'salary_history') }}

),

renamed as (

    select

        -- --- identifiers (FK to dim_member; pass-through, same-source) ------
        member_id,                                                   -- FK
        employer_id,                                                 -- FK

        -- --- effective dating ----------------------------------------------
        effective_date,

        -- --- measure (preserved; dirty values flagged by test, not fixed) --
        annual_salary,

        -- --- change reason (A: lower for enum consistency) -----------------
        lower(change_reason)         as change_reason,

        -- --- report timestamp (drives backdated detection downstream) ------
        reported_at,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed