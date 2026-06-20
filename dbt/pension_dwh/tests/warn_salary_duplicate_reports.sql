{{ config(severity='warn') }}
-- Data-quality monitor (warn) on staging: surfaces duplicate salary reports
-- — same natural key (member_id, employer_id, effective_date) submitted more
-- than once (resubmissions, differing reported_at). These are deduped before
-- the dimension (keep latest reported_at), so this does NOT block; it makes
-- the original duplicate volume visible for DQ trend tracking. Monitoring the
-- duplicates HERE (staging, 1:1 mirror) not on the dimension, because the
-- dimension has already removed them — salary_sk uniqueness guards the dim.
select
    member_id,
    employer_id,
    effective_date,
    count(*) as report_count
from {{ ref('stg_oncap__salary_history') }}
group by 1, 2, 3
having count(*) > 1