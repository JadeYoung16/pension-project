-- Every application_id in int_buyback_events must appear
-- exactly once here, and nothing else may appear.
-- (uniqueness is covered by the yml unique test)
select
    coalesce(e.application_id, a.application_id)
        as application_id,
    iff(a.application_id is null,
        'missing', 'extra') as problem
from (
    select distinct application_id
    from {{ ref('int_buyback_events') }}
) as e
full outer join {{ ref('int_buyback_applications') }} as a
    on e.application_id = a.application_id
where e.application_id is null
   or a.application_id is null