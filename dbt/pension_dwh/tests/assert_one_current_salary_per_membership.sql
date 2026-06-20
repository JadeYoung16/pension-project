-- SCD2 invariant: each membership has exactly one current version.
-- Returns violating memberships (>1 current) → fails if any row returned.
select
    member_id,
    employer_id,
    count(*) as current_count
from {{ ref('dim_salary_history') }}
where is_current = true
group by 1, 2
having count(*) > 1