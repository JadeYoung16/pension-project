-- ==========================================================================
-- stg_oncap__life_event
-- ==========================================================================
-- One row per member life event. 16,699 rows, 24 monthly files
-- (2022-02 to 2024-01).
--
-- Wide event table:
--   - BBK_* events (12,979 rows): buyback columns populated; costs mean
--     the whole application, except bbk_installment_pay (one payment)
--   - ADDR_CHG / BENE_UPD / MARITAL (3,720 rows): buyback columns NULL
--
-- Transformations:
--   - enum text columns lowercased (A: UPPERCASE -> lower)
--   - Y/N flags cast to boolean with to_boolean (fails loudly on any
--     value other than Y/N; try_to_boolean would silently return NULL)
--   - event_timestamp fixed and converted to UTC (see column comment)
--
-- Deliberately NOT done here (business rules, see _properties.yml):
--   - renaming event_date / event_timestamp (meaning not yet confirmed)
--   - splitting REJECTED out of bbk_approved
--   - identifying first vs resubmitted applications
--   - cleaning free-text notes
--
-- Case principle: see stg_oncap__employer_registry header.
-- ==========================================================================

with

source as (

    select * from {{ source('raw_oncap', 'life_event') }}

),

wall_clock as (

    -- Restore Toronto wall-clock time. Source labels it -05:00 all
    -- year (~10% of rows restate the same value as +00:00).
    -- Note: Etc/GMT+5 means UTC-5 (POSIX sign is inverted).
    select
        *,
        convert_timezone('Etc/GMT+5', event_timestamp)::timestamp_ntz
            as _wall_clock
    from source

),

renamed as (

    select

        -- --- identifiers -------------------------------------------------
        event_id,
        member_id,
        employer_id,

        -- --- temporal ----------------------------------------------------
        event_date,

        -- Rebuild as Toronto time so the tz database applies DST,
        -- then convert to UTC (TIMESTAMP_TZ, same as portal_event).
        -- Winter rows unchanged; DST rows move 1 hour earlier.
        convert_timezone(
            'UTC',
            timestamp_tz_from_parts(
                year(_wall_clock), month(_wall_clock),
                day(_wall_clock), hour(_wall_clock),
                minute(_wall_clock), second(_wall_clock),
                date_part(nanosecond, _wall_clock),
                'America/Toronto'
            )
        ) as event_timestamp,

        -- --- event classification ----------------------------------------
        lower(event_type_code) as event_type_code,
        lower(event_status) as event_status,
        lower(channel_code) as channel_code,

        -- --- buyback details (NULL for non-buyback events) ---------------
        lower(buyback_category_code) as buyback_category_code,
        buyback_service_years,
        leave_end_date,
        months_since_eligibility,
        to_boolean(is_within_window) as is_within_window,
        to_boolean(is_open_option) as is_open_option,

        -- --- cost breakdown (NULL for non-buyback events) ----------------
        member_cost,
        employer_cost,
        total_cost,

        -- --- payment terms (NULL for non-buyback events) -----------------
        lower(payment_method) as payment_method,
        installment_months,

        -- --- free text ---------------------------------------------------
        notes,

        -- --- audit -------------------------------------------------------
        _source_file as source_file,
        _row_num as source_row_num,
        _loaded_at as loaded_at

    from wall_clock

)

select * from renamed