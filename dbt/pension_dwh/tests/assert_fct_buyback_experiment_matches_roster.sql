-- Model keys must equal the roster exactly
-- (no member lost, none fanned out).
with roster as (
    select campaign_id, member_id
    from {{ ref('stg_oncap__campaign_assignment') }}
    where arm in ('treatment', 'control')
      and in_final_send_list
),
model as (
    select campaign_id, member_id
    from {{ ref('fct_buyback_experiment') }}
)
select
    coalesce(r.campaign_id, m.campaign_id)
        as campaign_id,
    coalesce(r.member_id, m.member_id)
        as member_id
from roster as r
full outer join model as m
    on  r.campaign_id = m.campaign_id
    and r.member_id = m.member_id
where r.member_id is null
   or m.member_id is null