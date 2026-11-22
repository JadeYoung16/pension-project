{{ config(materialized='table') }}

-- =============================================================
-- fct_buyback
-- Grain: one row per buyback application (PK application_id).
-- Adds to int_buyback_applications: point-in-time member /
-- employer SKs, app date SK, lag measures, furthest_stage,
-- and installment payment progress.
-- Experiment logic (e.g. cancel-and-resubmit counted outside
-- the window) lives in the experiment mart, not here.
-- =============================================================

with

applications as (

    select * from {{ ref('int_buyback_applications') }}

),

-- installment payments per application
-- one bbk_installment_pay row = one installment (verified on
-- completed installment apps: 12 rows for 12 months)
payments as (

    select
        application_id,
        count(*)        as n_payments,
        max(event_date) as last_payment_date
    from {{ ref('int_buyback_events') }}
    where event_type_code = 'bbk_installment_pay'
    group by application_id

),

final as (

    select
        -- keys
        a.application_id,
        a.application_seq,
        a.member_id,
        a.employer_id,

        -- point-in-time SKs, bound at app_date
        m.member_sk,
        e.employer_sk,
        cast(to_char(a.app_date, 'YYYYMMDD') as integer)
            as app_date_sk,

        -- milestones
        a.app_date,
        a.app_entered_at,
        a.quote_date,
        a.approved_date,
        a.rejected_date,
        a.completed_date,
        a.cancelled_date,

        -- status
        a.outcome,
        case
            when a.completed_date is not null then 'completed'
            when a.approved_date  is not null then 'approved'
            when a.quote_date     is not null then 'quoted'
            else 'applied'
        end as furthest_stage,

        -- lags (days)
        datediff('day', a.app_date, a.quote_date)
            as days_app_to_quote,
        datediff('day', a.quote_date, a.approved_date)
            as days_quote_to_approved,
        datediff('day', a.quote_date, a.rejected_date)
            as days_quote_to_rejected,
        datediff('day', a.app_date, a.completed_date)
            as days_app_to_completed,

        -- installment progress
        -- null = not applicable (lump sum); 0 = none paid yet
        case
            when a.installment_months is null then null
            else coalesce(p.n_payments, 0)
        end as installments_paid,
        p.last_payment_date,

        -- application attributes
        a.channel_code,
        a.buyback_category_code,
        a.buyback_service_years,
        a.leave_end_date,
        a.months_since_eligibility,
        a.is_within_window,
        a.is_open_option,
        a.member_cost,
        a.employer_cost,
        a.total_cost,
        a.payment_method,
        a.installment_months

    from applications as a

    left join payments as p
        on a.application_id = p.application_id

    left join {{ ref('dim_member') }} as m
        on a.member_id = m.member_id
        and a.employer_id = m.employer_id
        and a.app_date >= m.valid_from
        and a.app_date < coalesce(m.valid_to, '9999-12-31')

    left join {{ ref('dim_employer') }} as e
        on a.employer_id = e.employer_id
        and a.app_date >= e.valid_from
        and a.app_date < coalesce(e.valid_to, '9999-12-31')

)

select * from final