-- =============================================================================
-- stg_oncap__email_engagement
-- =============================================================================
-- One row per email event. Grain: event (not email).
-- 227,502 rows = ~50k unique emails × ~4.5 events per email funnel.
--
-- Event funnel:
--   SENT → DELIVERED → OPENED → CLICKED   (happy path)
--                    → BOUNCED             (delivery failure)
--                    → UNSUBSCRIBED        (CAN-SPAM compliance)
--
-- 1:1 mirror of raw with:
--   - lowercase normalization on event_type (A: UPPERCASE enum)
--   - preserve campaign_id as identifier (NOT lowered, treated as ID
--     not status enum; campaign count grows over time)
--   - preserve campaign_name (C: display, 1:1 with campaign_id —
--     normalization to dim_campaign deferred to mart layer)
--   - preserve link_url_clicked (URL, case-sensitive; NULL when
--     event_type != 'clicked', already cleanly NULL in raw)
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'email_engagement') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        event_id,
        member_id,                                                   -- FK
        campaign_id,                                                 -- identifier, not enum

        -- --- campaign metadata (preserved; 1:1 with campaign_id) -----------
        campaign_name,                                               -- C: display

        -- --- event details -------------------------------------------------
        lower(event_type)           as event_type,                   -- A: UPPERCASE -> lower
        event_timestamp,                                             -- already TIMESTAMP_TZ

        -- --- click-specific (NULL when event_type != 'clicked') ------------
        link_url_clicked,                                            -- URL, case-sensitive

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed