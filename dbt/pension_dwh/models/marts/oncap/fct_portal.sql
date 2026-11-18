{{
    config(
        materialized='incremental',
        unique_key='event_id',
        incremental_strategy='delete+insert'
    )
}}

-- ======================================================
-- fct_portal
-- ======================================================
-- Grain: one member portal event. Factless: count rows.
-- Uptime monitor traffic is excluded (not member
-- activity). event_date_sk uses the Toronto local date.
-- ======================================================

with

-- Incremental: 7-day look-back covers overlap between
-- runs; portal events do not arrive late.
source as (

    select *
    from {{ ref('stg_oncap__portal_event') }}
    where not is_uptime_monitor

    {% if is_incremental() %}
    and event_timestamp >= (    -- noqa: LT02
        select dateadd('day', -7, max(event_timestamp))    -- noqa: LT02
        from {{ this }}    -- noqa: LT02
    )    -- noqa: LT02
    {% endif %}

),

-- Point-in-time join to dim_member.
joined as (

    select
        s.*,
        m.member_sk

    from source s

    left join {{ ref('dim_member') }} m
        on s.member_id = m.member_id  -- noqa: LT02
        and s.event_timestamp >= m.valid_from
        and s.event_timestamp < coalesce(m.valid_to, '9999-12-31')  -- noqa: LT02

),

final as (

    select
        -- PK
        event_id,

        -- foreign keys
        member_sk,
        cast(to_char(
            convert_timezone('America/Toronto',
                event_timestamp),
            'YYYYMMDD') as integer) as event_date_sk,

        -- degenerate dimensions
        event_type,
        session_id,
        page_path,
        event_timestamp,

        -- device type derived from user_agent;
        -- unmapped values pass through so that
        -- accepted_values flags them
        case
            when user_agent = 'unknown' then 'Unknown'
            when user_agent ilike '%iphone%'
                or user_agent ilike '%ipad%'
                or user_agent ilike '%(ios %'
                then 'Mobile-iOS'
            when user_agent ilike '%android%'
                then 'Mobile-Android'
            when user_agent ilike '%windows%'
                or user_agent ilike '%macintosh%'
                then 'Desktop'
            else user_agent
        end as device_type,

        -- audit
        source_file,
        source_row_num

    from joined

)

select * from final