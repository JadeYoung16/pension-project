{{ config(severity='warn') }}

-- Business-process rules within one application.
-- A failure means the upstream process changed,
-- not that the tagging logic broke.
with per_app as (
    select
        application_id,
        count_if(event_type_code = 'bbk_quote')
            as n_quote,
        count_if(event_type_code = 'bbk_approved')
            as n_approved,
        count_if(event_type_code = 'bbk_complete')
            as n_complete,
        count_if(event_type_code = 'bbk_cancelled')
            as n_cancelled,
        min(iff(event_type_code = 'bbk_quote',
            event_timestamp, null)) as quote_ts,
        min(iff(event_type_code = 'bbk_approved',
            event_timestamp, null)) as approved_ts,
        min(iff(event_type_code = 'bbk_complete',
            event_timestamp, null)) as complete_ts,
        min(iff(event_type_code = 'bbk_cancelled',
            event_timestamp, null)) as cancelled_ts,
        max(event_timestamp) as last_ts
    from {{ ref('int_buyback_events') }}
    group by application_id
)

select application_id, 'duplicate_step' as reason
from per_app
where n_quote > 1 or n_approved > 1
   or n_complete > 1 or n_cancelled > 1

union all

select application_id, 'skipped_step'
from per_app
where (n_approved > 0 and n_quote = 0)
   or (n_complete > 0 and n_approved = 0)

union all

select application_id, 'out_of_order'
from per_app
where quote_ts > approved_ts
   or approved_ts > complete_ts

union all

select application_id, 'event_after_cancel'
from per_app
where cancelled_ts < last_ts