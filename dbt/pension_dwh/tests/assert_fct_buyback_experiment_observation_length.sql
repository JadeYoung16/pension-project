-- Period length must follow the var.
select campaign_id, member_id
from {{ ref('fct_buyback_experiment') }}
where observation_end_date <> dateadd('day',
    {{ var('experiment_observation_days') }} - 1,
    observation_start_date)