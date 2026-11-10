-- Tagging depends on a strict order by event_timestamp
-- within a member. A tie makes the assignment arbitrary.
select member_id, event_timestamp, count(*) as n
from {{ ref('int_buyback_events') }}
group by member_id, event_timestamp
having count(*) > 1