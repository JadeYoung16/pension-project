-- Composite referential integrity: every (member_id, employer_id) must exist
-- in the member roster. Catches "valid member under wrong employer" orphans
-- that a single-field relationships test cannot. Currently returns 0
-- (orphans are member_id 50001-59999, fully absent); this is future-proofing.
select
    s.salary_sk,
    s.member_id,
    s.employer_id
from {{ ref('dim_salary_history') }} as s
where not exists (
    select 1
    from {{ ref('stg_oncap__member_census') }} as m
    where m.member_id = s.member_id
      and m.employer_id = s.employer_id
)