-- =============================================================================
-- stg_oncap__life_event
-- =============================================================================
-- One row per member life event. 17,638 rows.
--
-- This is a "wide event table" — different event_type_code values use
-- different column subsets:
--
--   Buyback events (80%, 14,178 rows):
--     BBK_APP, BBK_QUOTE, BBK_APPROVED, BBK_CANCELLED, BBK_COMPLETE,
--     BBK_INSTALLMENT_PAY
--     → populated: buyback_category_code, member/employer/total_cost,
--                  buyback_service_years, payment_method, etc.
--
--   Non-buyback events (20%, 3,720 rows):
--     ADDR_CHG (address change), BENE_UPD (beneficiary update), MARITAL
--     → buyback columns are NULL (by design, not data quality issue)
--
-- 1:1 mirror of raw with:
--   - lowercase normalization on enum text columns (A: UPPERCASE -> lower)
--   - preserve Y/N flags (is_within_window, is_open_option)
--   - preserve numeric columns (no cast)
--   - cast nothing (raw types already correct: DATE/NUMBER/VARCHAR/TIMESTAMP_TZ)
--
-- Case principle: see stg_oncap__employer_registry header for A/B/C taxonomy.
--
-- Business consistency (future singular tests, Week 9 polish):
--   - BBK_* event_type → buyback_category_code must be NOT NULL
--   - non-BBK event_type → buyback columns must all be NULL
--   - total_cost should equal member_cost + employer_cost
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'life_event') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        event_id,
        member_id,                                                   -- FK
        employer_id,                                                 -- FK

        -- --- temporal ------------------------------------------------------
        event_date,
        event_timestamp,                                             -- TIMESTAMP_TZ

        -- --- event classification (A: UPPERCASE -> lower) ------------------
        lower(event_type_code)      as event_type_code,
        lower(event_status)         as event_status,
        lower(channel_code)         as channel_code,

        -- --- buyback details (NULL for non-buyback events; A: lower) -------
        lower(buyback_category_code) as buyback_category_code,
        buyback_service_years,                                       -- numeric
        leave_end_date,                                              -- DATE, NULL allowed
        months_since_eligibility,                                    -- numeric
        is_within_window,                                            -- Y/N flag, preserved
        is_open_option,                                              -- Y/N flag, preserved

        -- --- cost breakdown (NULL for non-buyback events) ------------------
        member_cost,
        employer_cost,
        total_cost,                                                  -- = member + employer (raw invariant)

        -- --- payment terms (NULL for non-buyback events; A: lower) ---------
        lower(payment_method)       as payment_method,
        installment_months,                                          -- numeric, NULL when LUMP_SUM

        -- --- free text -----------------------------------------------------
        notes,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed