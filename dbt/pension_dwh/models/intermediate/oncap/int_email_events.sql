{{ config(materialized='table') }}

-- ======================================================
-- int_email_events
-- ======================================================
-- Grain: one email event (all event types).
-- PK = event_id. Row count = staging.
--
-- Adds bot detection for opened / clicked:
--   - Apple Mail Privacy Protection pre-loads
--     messages on delivery (opens).
--   - Corporate security gateways scan links on
--     delivery (clicks).
-- Rule: gap from the prior delivery to the event
-- is below a threshold (dbt vars).
--
-- "Prior delivery" = most recent delivered event
-- for the same member and campaign at or before
-- this event. Campaigns send repeatedly, so the
-- first delivery would be wrong. There is no
-- message id, so an open of an older message
-- right after a new delivery can be misflagged
-- (rare).
--
-- No bot unsubscribes observed; unsubscribed and
-- other non open/click events get NULL.
-- Timestamps stay UTC; event_date_local is the
-- Toronto date.
-- ======================================================

with

source as (

    select * from {{ ref('stg_oncap__email_engagement') }}

),

-- Delivered events sort before other events at the
-- same timestamp, so a same-second open finds it.
with_prior_delivery as (

    select
        *,
        last_value(
            iff(event_type = 'delivered',
                event_timestamp, null)
        ) ignore nulls over (
            partition by member_id, campaign_id
            order by
                event_timestamp,
                iff(event_type = 'delivered', 0, 1)
            rows between unbounded preceding
                and current row
        ) as prior_delivered_at
    from source

),

with_gap as (

    select
        *,
        iff(event_type in ('opened', 'clicked'),
            prior_delivered_at, null)
            as last_delivered_at
    from with_prior_delivery

),

final as (

    select
        * exclude (prior_delivered_at),

        convert_timezone('America/Toronto',
            event_timestamp)::date
            as event_date_local,

        datediff('second', last_delivered_at,
            event_timestamp)
            as seconds_since_delivered,

        case event_type
            when 'opened' then
                datediff('second', last_delivered_at,
                    event_timestamp)
                < {{ var('bot_open_threshold_seconds') }}
            when 'clicked' then
                datediff('second', last_delivered_at,
                    event_timestamp)
                < {{ var('bot_click_threshold_seconds') }}
        end as is_suspected_bot

    from with_gap

)

select * from final