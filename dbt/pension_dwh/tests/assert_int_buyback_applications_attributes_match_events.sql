-- Every BBK event must carry the same application
-- attributes as its application's bbk_app row.
-- Amounts are skipped on installment rows (single payment).
-- channel_code is excluded on purpose (system events).
select
    e.event_id,
    e.event_type_code,
    e.application_id
from {{ ref('int_buyback_events') }} as e
inner join {{ ref('int_buyback_applications') }} as a
    on e.application_id = a.application_id
where e.member_id is distinct from a.member_id
   or e.employer_id is distinct from a.employer_id
   or e.buyback_category_code
        is distinct from a.buyback_category_code
   or e.buyback_service_years
        is distinct from a.buyback_service_years
   or e.leave_end_date
        is distinct from a.leave_end_date
   or e.months_since_eligibility
        is distinct from a.months_since_eligibility
   or e.is_within_window
        is distinct from a.is_within_window
   or e.is_open_option
        is distinct from a.is_open_option
   or e.payment_method
        is distinct from a.payment_method
   or e.installment_months
        is distinct from a.installment_months
   or (
        e.event_type_code <> 'bbk_installment_pay'
        and (
            e.member_cost is distinct from a.member_cost
            or e.employer_cost
                is distinct from a.employer_cost
            or e.total_cost is distinct from a.total_cost
        )
   )