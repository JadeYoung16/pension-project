-- =============================================================
-- int_buyback_applications
-- Grain: one row per buyback application (PK application_id).
-- Attributes come from the application's bbk_app row, not
-- aggregated across events: max() picks by alphabet, so
-- channel 'system' would beat 'mail' / 'portal'.
-- Milestone dates use event_date; the app's entry timestamp
-- is kept separately (paper apps are entered 7-21 days late).
-- bbk_approved is split by event_status: approved / rejected.
-- outcome = furthest step reached. No business thresholds
-- (e.g. "abandoned after N days") here; those belong in marts.
-- =============================================================

with

events as (

    select * from {{ ref('int_buyback_events') }}

),

-- one row per application: the member's submitted application
applications as (

    select
        application_id,
        application_seq,
        member_id,
        employer_id,
        channel_code,
        event_date      as app_date,
        event_timestamp as app_entered_at,
        buyback_category_code,
        buyback_service_years,
        leave_end_date,
        months_since_eligibility,
        is_within_window,
        is_open_option,
        member_cost,
        employer_cost,
        total_cost,
        payment_method,
        installment_months
    from events
    where event_type_code = 'bbk_app'

),

-- one date per milestone; at most one of each per application
-- (guarded by assert_int_buyback_events_application_flow)
milestones as (

    select
        application_id,
        max(iff(event_type_code = 'bbk_quote',
                event_date, null)) as quote_date,
        max(iff(event_type_code = 'bbk_approved'
                    and event_status = 'approved',
                event_date, null)) as approved_date,
        max(iff(event_type_code = 'bbk_approved'
                    and event_status = 'rejected',
                event_date, null)) as rejected_date,
        max(iff(event_type_code = 'bbk_complete',
                event_date, null)) as completed_date,
        max(iff(event_type_code = 'bbk_cancelled',
                event_date, null)) as cancelled_date
    from events
    group by application_id

),

final as (

    select
        a.application_id,
        a.application_seq,
        a.member_id,
        a.employer_id,
        a.channel_code,

        -- milestones
        a.app_date,
        a.app_entered_at,
        m.quote_date,
        m.approved_date,
        m.rejected_date,
        m.completed_date,
        m.cancelled_date,

        case
            when m.completed_date is not null then 'completed'
            when m.rejected_date  is not null then 'rejected'
            when m.cancelled_date is not null then 'cancelled'
            when m.approved_date  is not null then 'approved'
            when m.quote_date     is not null then 'quoted'
            else 'applied'
        end as outcome,

        -- application attributes
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
    inner join milestones as m
        on a.application_id = m.application_id

)

select * from final