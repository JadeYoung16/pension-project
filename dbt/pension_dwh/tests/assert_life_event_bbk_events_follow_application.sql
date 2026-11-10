{{ config(severity='error') }}

-- Every buyback event other than the application itself must have
-- an application (bbk_app) by the same member entered at or before
-- it. Ordered by entry time, not event_date: paper applications
-- are dated on receipt, which can make them look out of order.

with bbk as (
    select member_id, event_id, event_type_code, event_timestamp
    from {{ ref('stg_oncap__life_event') }}
    where event_type_code like 'bbk%'
),

apps as (
    select member_id, event_timestamp
    from bbk
    where event_type_code = 'bbk_app'
)

select b.*
from bbk as b
where b.event_type_code <> 'bbk_app'
  and not exists (
      select 1
      from apps as a
      where a.member_id = b.member_id
        and a.event_timestamp <= b.event_timestamp
  )