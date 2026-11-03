-- ======================================================
-- stg_oncap__portal_event
-- ======================================================
-- One row per portal event. Grain: event. PK: event_id.
--
-- - Rows that failed JSON parsing are excluded
--   (_raw_line is not null). Monitored by a source test.
-- - event_timestamp converted to UTC: web rows arrive
--   in Toronto local time, app rows in UTC.
-- - UTM parsed from page_location, or from the decoded
--   Outlook safelinks referrer.
-- - Uptime monitor rows are flagged, not removed.
--
-- Full notes in _properties.yml.
-- ======================================================

with

source as (

    select *
    from {{ source('raw_oncap', 'portal_event') }}
    where _raw_line is null

),

parsed as (

    select
        *,
        event_properties:page_location::string
            as page_location,
        iff(referrer ilike '%safelinks.protection.outlook%',
            parse_url(referrer):parameters:url::string,
            null) as safelinks_encoded,
        coalesce(user_agent ilike '%monitor%', false)
            as is_uptime_monitor
    from source

),

decoded as (

    select
        *,
        regexp_replace(
         regexp_replace(
          regexp_replace(
           regexp_replace(
            regexp_replace(safelinks_encoded,
             '%3A', ':', 1, 0, 'i'),
            '%2F', '/', 1, 0, 'i'),
           '%3F', '?', 1, 0, 'i'),
          '%3D', '=', 1, 0, 'i'),
         '%26', '&', 1, 0, 'i')
            as safelinks_target_url
    from parsed

),

utm as (

    select
        *,
        case
            when page_location ilike '%utm_%'
                then 'page_location'
            when safelinks_target_url ilike '%utm_%'
                then 'safelinks_referrer'
        end as utm_found_in,
        parse_url(case utm_found_in
            when 'page_location' then page_location
            else safelinks_target_url
        end):parameters as utm_params
    from decoded

),

renamed as (

    select

        -- identifiers
        event_id,
        member_id,
        session_id,

        -- temporal (UTC)
        convert_timezone('UTC', event_timestamp)
            as event_timestamp,

        -- event classification
        event_type,
        page_path,
        referrer,

        -- traffic source
        page_location,
        safelinks_target_url,
        utm_found_in,
        utm_params:utm_source::string as utm_source,
        utm_params:utm_medium::string as utm_medium,
        lower(utm_params:utm_campaign::string)
            as utm_campaign,

        -- technical fingerprinting (PII)
        ip_hash,
        coalesce(user_agent, 'unknown') as user_agent,
        is_uptime_monitor,

        -- semi-structured
        event_properties,

        -- audit
        _source_file as source_file,
        _row_num as source_row_num,
        _loaded_at as loaded_at

    from utm

)

select * from renamed