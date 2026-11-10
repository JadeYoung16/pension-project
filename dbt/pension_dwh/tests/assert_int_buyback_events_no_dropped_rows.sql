-- Every staging row carrying buyback attributes must
-- appear here. Uses buyback_category_code instead of the
-- event-type filter, so a wrong filter cannot hide itself.
select s.event_id, s.event_type_code
from {{ ref('stg_oncap__life_event') }} s
left join {{ ref('int_buyback_events') }} i
    on s.event_id = i.event_id
where s.buyback_category_code is not null
  and i.event_id is null