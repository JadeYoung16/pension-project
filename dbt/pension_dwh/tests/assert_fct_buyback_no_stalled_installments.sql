{{ config(severity='warn') }}

-- In-progress installment applications (outcome = 'approved')
-- with no payment for more than 90 days (two missed monthly
-- installments). Normal gap is 30 days (max observed 30).
-- Measured against the data's last event date, not
-- current_date, so a static dataset does not trip the test.

with data_end as (

    select max(event_date) as last_event_date
    from {{ ref('int_buyback_events') }}

)

select
    f.application_id,
    f.approved_date,
    f.last_payment_date,
    datediff(
        'day',
        coalesce(f.last_payment_date, f.approved_date),
        e.last_event_date
    ) as days_since_last_activity
from {{ ref('fct_buyback') }} as f
cross join data_end as e
where f.outcome = 'approved'
  and datediff(
        'day',
        coalesce(f.last_payment_date, f.approved_date),
        e.last_event_date
      ) > 90