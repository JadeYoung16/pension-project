-- is_suspected_bot must match the threshold vars.
-- Catches logic changed in the model without
-- changing the vars.
select
    event_id,
    event_type,
    seconds_since_delivered,
    is_suspected_bot
from {{ ref('int_email_events') }}
where
    (event_type = 'opened'
     and is_suspected_bot is distinct from (
         seconds_since_delivered
         < {{ var('bot_open_threshold_seconds') }}))
    or
    (event_type = 'clicked'
     and is_suspected_bot is distinct from (
         seconds_since_delivered
         < {{ var('bot_click_threshold_seconds') }}))