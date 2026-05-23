-- Test fails if (member_id, employer_id) is not unique in member_census
select
    member_id,
    employer_id,
    count(*) as n
from {{ ref('stg_oncap__member_census') }}
group by member_id, employer_id
having count(*) > 1