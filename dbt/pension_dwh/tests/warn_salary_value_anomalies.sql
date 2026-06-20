{{ config(severity='warn') }}
-- Data-quality monitor (warn, not error): surfaces legitimate-but-anomalous
-- salary values kept in the dimension by design — negative (payroll reversal)
-- and 10x outliers (fat-finger). Visible in CI without blocking the build.
-- NULL (missing report) is excluded here; it is expected and not anomalous.
select
    salary_sk,
    member_id,
    employer_id,
    effective_date,
    annual_salary,
    change_reason
from {{ ref('dim_salary_history') }}
where annual_salary < 0
   or annual_salary > 500000