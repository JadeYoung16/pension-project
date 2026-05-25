-- =============================================================================
-- stg_oncap__portal_event
-- =============================================================================
-- One row per portal interaction event. Grain: event.
-- 58,537 rows.
--
-- Known raw layer incompleteness:
--   Day 5 COPY INTO from 91 jsonl files partial-loaded due to malformed JSON.
--   Expected ~59,606 rows (Postgres equivalent); 1,069 rows (1.8%) skipped.
--   Week 9 polish: TRY_PARSE_JSON re-ingestion to recover.
--
-- 1:1 mirror of raw with:
--   - preserve event_type as-is (raw already lowercased)
--   - preserve event_properties as VARIANT (downstream flattens per-event-type)
--   - preserve all PII fields (ip_hash already pre-hashed; flagged in yaml)
--   - cast nothing (raw types already correct: VARCHAR/TIMESTAMP_TZ/VARIANT)
--
-- Generator artifacts (Week 9 polish backlog):
--   - referrer is 100% NULL — generator does not populate
--   - user_agent has only 4 unique values — simplified device modeling
--   - page_path is redundant with event_type (1:1 derivable) — kept for fidelity
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'portal_event') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        event_id,
        member_id,                                                   -- FK
        session_id,                                                  -- session grouping key

        -- --- temporal ------------------------------------------------------
        event_timestamp,                                             -- already TIMESTAMP_TZ

        -- --- event classification (raw already lowercase) ------------------
        event_type,                                                  -- 8 distinct values
        page_path,                                                   -- 1:1 with event_type (raw artifact)
        referrer,                                                    -- 100% NULL currently

        -- --- PII: technical fingerprinting (preserved; flagged) ------------
        ip_hash,                                                     -- already sha256-hashed
        user_agent,

        -- --- semi-structured properties ------------------------------------
        event_properties,                                            -- VARIANT, conditional sub-fields

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed