-- =============================================================================
-- stg_oncap__email_engagement
-- =============================================================================
-- One row per email event. Grain: event. PK = event_id.
-- Covers all campaigns in the ESP export (no business filtering here).
--
-- Event funnel:
--   SENT → DELIVERED → OPENED → CLICKED   (happy path)
--        → BOUNCED                         (delivery failure)
--   UNSUBSCRIBED                           (compliance)
--
-- Transformations:
--   1. Dedup on event_id. Raw contains exact duplicate rows (ESP webhook
--      re-delivery, 2 copies, same file). Keep the first copy by
--      (_source_file, _row_num) so the result is deterministic.
--      Assumption that copies are identical is enforced by
--      tests/assert_email_engagement_duplicate_ids_identical.sql (on source).
--   2. event_type lowercased (raw is UPPERCASE).
--   3. bounce_type: ESP added this column in the 2023-09 export. Earlier
--      files have no bounce classification, so bounced events from those
--      files are set to 'unknown'. Non-bounce events stay NULL
--      (NULL = not applicable, 'unknown' = bounce with no classification).
--
-- Not done here (business rules → intermediate):
--   - suspected bot opens / clicks (delivery-to-open gap heuristic)
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'email_engagement') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by event_id
        order by _source_file, _row_num
    ) = 1

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        event_id,
        member_id,                                                   -- FK
        campaign_id,                                                 -- identifier, not enum

        -- --- campaign metadata (1:1 with campaign_id) ----------------------
        campaign_name,

        -- --- event details -------------------------------------------------
        lower(event_type)           as event_type,                   -- UPPERCASE -> lower
        event_timestamp,                                             -- TIMESTAMP_TZ, UTC

        -- --- type-specific columns -----------------------------------------
        link_url_clicked,                                            -- clicked only
        case
            when lower(event_type) = 'bounced' and bounce_type is null
                then 'unknown'
            else bounce_type
        end                         as bounce_type,                  -- bounced only

        -- --- audit pass-through --------------------------------------------
        _source_file                as source_file,
        _row_num                    as source_row_num,
        _loaded_at                  as loaded_at

    from deduplicated

)

select * from renamed