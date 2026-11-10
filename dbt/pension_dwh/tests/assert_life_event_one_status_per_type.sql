{{ config(severity='error') }}

-- Each event type carries a single status, except bbk_approved,
-- which holds the review decision (approved or rejected).

with events as (
    select * from {{ ref('stg_oncap__life_event') }}
),

multi_status as (
    select
        event_type_code,
        'more than one status' as problem
    from events
    where event_type_code <> 'bbk_approved'
    group by 1
    having count(distinct event_status) > 1
),

bad_decision as (
    select distinct
        event_type_code,
        'unexpected status: ' || event_status as problem
    from events
    where event_type_code = 'bbk_approved'
      and event_status not in ('approved', 'rejected')
)

select * from multi_status
union all
select * from bad_decision