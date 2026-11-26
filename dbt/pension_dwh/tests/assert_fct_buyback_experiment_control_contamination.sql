{{ config(severity='warn') }}

-- Control members delivered the email during the
-- period. Kept as control (ITT); warn only when
-- the share exceeds 1% (currently 24 / 2,782).
select
    campaign_id,
    count_if(first_delivered_date is not null)
        / count(*) as contaminated_share
from {{ ref('fct_buyback_experiment') }}
where arm = 'control'
group by 1
having count_if(first_delivered_date is not null)
    / count(*) > 0.01