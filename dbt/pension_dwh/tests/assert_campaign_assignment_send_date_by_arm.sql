-- Each arm has exactly one send date per campaign,
-- and control is sent after treatment (delayed send).
with

arm_dates as (

    select
        campaign_id,
        arm,
        count(distinct scheduled_send_date) as n_dates,
        min(scheduled_send_date)            as send_date
    from {{ ref('stg_oncap__campaign_assignment') }}
    group by 1, 2

)

select campaign_id, arm, 'multiple send dates in arm' as issue
from arm_dates
where n_dates > 1

union all

select c.campaign_id, c.arm, 'control not sent after treatment' as issue
from arm_dates as c
inner join arm_dates as t
    on  c.campaign_id = t.campaign_id
    and t.arm = 'treatment'
where c.arm = 'control'
  and c.send_date <= t.send_date