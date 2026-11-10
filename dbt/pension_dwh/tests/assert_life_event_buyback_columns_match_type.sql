{{ config(severity='error') }}

-- Non-buyback events: every buyback column is NULL.
-- Buyback events: core application attributes are populated
-- (they are copied onto every event of the application).

select
    event_id,
    event_type_code
from {{ ref('stg_oncap__life_event') }}
where
    (
        event_type_code not like 'bbk%'
        and (
            buyback_category_code is not null
            or buyback_service_years is not null
            or leave_end_date is not null
            or months_since_eligibility is not null
            or is_within_window is not null
            or is_open_option is not null
            or member_cost is not null
            or employer_cost is not null
            or total_cost is not null
            or payment_method is not null
            or installment_months is not null
        )
    )
    or (
        event_type_code like 'bbk%'
        and (
            buyback_category_code is null
            or buyback_service_years is null
            or is_within_window is null
            or is_open_option is null
            or member_cost is null
            or employer_cost is null
            or total_cost is null
            or payment_method is null
        )
    )