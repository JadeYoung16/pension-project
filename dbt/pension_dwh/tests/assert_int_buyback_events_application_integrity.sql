-- Structural rules for application tagging.
with e as (
    select * from {{ ref('int_buyback_events') }}
),

apps as (
    select event_id, member_id
    from e
    where event_type_code = 'bbk_app'
)

-- application_id must be a bbk_app of the same member
select e.event_id as id, 'not_own_app' as reason
from e
left join apps a
    on e.application_id = a.event_id
    and e.member_id = a.member_id
where a.event_id is null

union all

-- a bbk_app opens its own application
-- (this also means one bbk_app per application)
select event_id, 'app_not_self'
from e
where event_type_code = 'bbk_app'
  and application_id != event_id

union all

-- one seq per application
select application_id, 'multiple_seq'
from e
group by application_id
having count(distinct application_seq) > 1