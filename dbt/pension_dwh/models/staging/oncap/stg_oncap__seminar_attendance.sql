-- =============================================================================
-- stg_oncap__seminar_attendance
-- =============================================================================
-- One row per seminar registration (registered + showed-up flag separate).
-- 5,816 rows. 1:1 mirror of raw with:
--   - lowercase normalization on enum text columns (topic, format)
--   - preserve seminar_location (city names; display-bound, C-class)
--   - preserve attended_flag (Y/N, 2-value, no normalization needed)
--   - cast nothing (raw types already correct: DATE/VARCHAR)
--
-- Case principle: see stg_oncap__employer_registry header for full A/B/C taxonomy.
--
-- Business note:
--   When attendance_format = 'virtual', seminar_location = 'Virtual'
--   (deterministic upstream relationship). Future singular test could
--   enforce this consistency; deferred to Week 9 polish.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'seminar_attendance') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        attendance_id,
        member_id,                                                   -- FK

        -- --- temporal ------------------------------------------------------
        registration_date,
        seminar_date,

        -- --- seminar attributes (A: UPPERCASE enum -> lower) ---------------
        lower(seminar_topic)        as seminar_topic,
        lower(attendance_format)    as attendance_format,

        -- --- location (C: city names, display-bound, preserved) ------------
        seminar_location,                                            -- C: Toronto, Kingston, etc.
                                                                     -- 'Virtual' when format=virtual  -- noqa: LT02

        -- --- attendance flag (Y/N preserved, only 2 values) ----------------
        attended_flag,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed
