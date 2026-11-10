-- int_buyback_events
-- One row per buyback event (bbk_*), tagged with the
-- application it belongs to.
-- Rule: each bbk_app opens a new application; every later
-- bbk event of the same member belongs to it until the
-- next bbk_app. Ordered by event_timestamp (entry time):
-- event_date is the receipt date and paper-mail lag
-- distorts its order.

with

bbk_events as (

    select *
    from {{ ref('stg_oncap__life_event') }}
    where event_type_code like 'bbk%'

),

tagged as (

    select
        *,

        -- number of applications opened so far
        sum(iff(event_type_code = 'bbk_app', 1, 0)) over (
            partition by member_id
            order by event_timestamp
            rows between unbounded preceding and current row
        ) as application_seq,

        -- event_id of the latest bbk_app at or before
        -- this event
        last_value(
            iff(event_type_code = 'bbk_app', event_id, null)
        ) ignore nulls over (
            partition by member_id
            order by event_timestamp
            rows between unbounded preceding and current row
        ) as application_id

    from bbk_events

)

select
    event_id,
    application_id,
    application_seq,
    * exclude (event_id, application_id, application_seq)
from tagged