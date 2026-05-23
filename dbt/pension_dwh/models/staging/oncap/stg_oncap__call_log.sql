-- =============================================================================
-- stg_oncap__call_log
-- =============================================================================
-- One row per member-to-call-center call. 4,122 rows.
-- 1:1 mirror of raw with:
--   - lowercase normalization on enum text columns (category, subcategory,
--     resolution_code; following stg_oncap__employer_registry A/B/C principle)
--   - preserve member_id, agent_id as-is (identifiers)
--   - preserve csat_score NULL semantics (NULL = no survey response, valid)
--   - cast nothing (raw types already correct)
--
-- FK note:
--   member_id → stg_oncap__member_census.member_id
--   The `relationships` test for this FK is deferred until
--   stg_oncap__member_census is built later in Week 5.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'call_log') }}

),

renamed as (

    select

        -- --- identifiers (preserved) ---------------------------------------
        call_id,
        member_id,                                         -- FK (member_census)
        agent_id,                                          -- FK to call-center agent
                                                           -- (no agent dim table; preserved as semi-structured ID)

        -- --- temporal ------------------------------------------------------
        call_timestamp,                                    -- already TIMESTAMP_TZ
        duration_seconds,

        -- --- call categorization (A: UPPERCASE enum → lower) ---------------
        lower(call_reason_category)     as call_reason_category,
        lower(call_reason_subcategory)  as call_reason_subcategory,
        lower(resolution_code)          as resolution_code,

        -- --- CSAT (preserve NULL: legitimate "no response" signal) ---------
        csat_score,

        -- --- free text (display-bound, preserved) --------------------------
        notes,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed