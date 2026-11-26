{{ config(materialized='table') }}

-- ======================================================
-- fct_buyback_experiment
-- ======================================================
-- Grain: one experiment member per campaign.
-- PK = (campaign_id, member_id).
-- Roster: treatment + control in the final send
-- list (guardrail and pre-assignment applicants
-- excluded).
--
-- Observation period: from the treatment send
-- date, var experiment_observation_days long,
-- shared by both arms. Control is sent after it
-- ends (delayed send). All funnel columns count
-- only events in this period (Toronto dates).
--
-- Primary metric (ITT): first_app_date is not
-- null = applied in the period, even if later
-- cancelled. Exclude applied_before_send = true
-- from the main analysis.
-- ======================================================

with

assignment as (

    select * from {{ ref('stg_oncap__campaign_assignment') }}

),

treatment_send as (

    select
        campaign_id,
        max(scheduled_send_date) as treatment_send_date
    from assignment
    where arm = 'treatment'
    group by 1

),

observation as (

    select
        campaign_id,
        treatment_send_date as observation_start_date,
        dateadd('day',
            {{ var('experiment_observation_days') }} - 1,
            treatment_send_date)
            as observation_end_date
    from treatment_send

),

roster as (

    select
        a.campaign_id,
        a.member_id,
        a.arm,
        a.segment,
        a.assigned_date,
        a.scheduled_send_date,
        o.observation_start_date,
        o.observation_end_date
    from assignment as a
    inner join observation as o
        on a.campaign_id = o.campaign_id
    where a.arm in ('treatment', 'control')
      and a.in_final_send_list

),

applications as (

    select * from {{ ref('fct_buyback') }}

),

-- Applied between assignment and the send date.
before_send as (

    select distinct
        r.campaign_id,
        r.member_id
    from roster as r
    inner join applications as a
        on  a.member_id = r.member_id
        and a.app_date >= r.assigned_date
        and a.app_date < r.observation_start_date

),

-- First application in the period; later funnel
-- steps follow this application.
first_app as (

    select
        r.campaign_id,
        r.member_id,
        a.application_id,
        a.app_date,
        a.quote_date,
        a.approved_date,
        a.furthest_stage,
        a.outcome
    from roster as r
    inner join applications as a
        on  a.member_id = r.member_id
        and a.app_date between r.observation_start_date
                           and r.observation_end_date
    qualify row_number() over (
        partition by r.campaign_id, r.member_id
        order by a.app_date, a.app_entered_at,
                 a.application_id
    ) = 1

),

-- Suspected bot opens / clicks excluded. A NULL
-- flag (no prior delivery) is not counted.
email as (

    select
        r.campaign_id,
        r.member_id,
        min(iff(e.event_type = 'delivered',
            e.event_date_local, null))
            as first_delivered_date,
        min(iff(e.event_type = 'opened'
                and not e.is_suspected_bot,
            e.event_date_local, null))
            as first_human_open_date,
        min(iff(e.event_type = 'clicked'
                and not e.is_suspected_bot,
            e.event_date_local, null))
            as first_human_click_date
    from roster as r
    inner join {{ ref('int_email_events') }} as e
        on  e.member_id = r.member_id
        and e.campaign_id = r.campaign_id
        and e.event_date_local
            between r.observation_start_date
                and r.observation_end_date
    group by 1, 2

),

-- Logged-in views only; member_sk -> member_id
-- is many-to-one (safe).
portal_views as (

    select
        m.member_id,
        to_date(p.event_date_sk::varchar, 'YYYYMMDD')
            as view_date
    from {{ ref('fct_portal') }} as p
    inner join {{ ref('dim_member') }} as m
        on m.member_sk = p.member_sk
    where p.event_type = 'buyback_info_page_view'

),

page as (

    select
        r.campaign_id,
        r.member_id,
        min(v.view_date) as first_buyback_page_view_date
    from roster as r
    inner join portal_views as v
        on  v.member_id = r.member_id
        and v.view_date between r.observation_start_date
                            and r.observation_end_date
    group by 1, 2

),

final as (

    select
        -- PK
        r.campaign_id,
        r.member_id,

        -- foreign keys (as of assigned_date)
        m.member_sk,
        emp.employer_sk,

        -- assignment
        r.arm,
        r.segment,
        r.assigned_date,
        r.scheduled_send_date,

        -- observation period (end date inclusive)
        r.observation_start_date,
        r.observation_end_date,

        -- flags
        bs.member_id is not null as applied_before_send,

        -- funnel (dates within the period)
        em.first_delivered_date,
        em.first_human_open_date,
        em.first_human_click_date,
        pg.first_buyback_page_view_date,
        fa.app_date        as first_app_date,
        fa.application_id  as first_app_id,

        -- follow-up of the first application
        -- (not cut at the period end)
        fa.quote_date      as first_app_quote_date,
        fa.approved_date   as first_app_approved_date,
        fa.furthest_stage  as first_app_furthest_stage,
        fa.outcome         as first_app_outcome

    from roster as r
    left join {{ ref('dim_member') }} as m
        on  m.member_id = r.member_id
        and r.assigned_date >= m.valid_from
        and r.assigned_date
            < coalesce(m.valid_to, '9999-12-31')
    left join {{ ref('dim_employer') }} as emp
        on  emp.employer_id = m.employer_id
        and r.assigned_date >= emp.valid_from
        and r.assigned_date
            < coalesce(emp.valid_to, '9999-12-31')
    left join before_send as bs
        on  bs.campaign_id = r.campaign_id
        and bs.member_id = r.member_id
    left join first_app as fa
        on  fa.campaign_id = r.campaign_id
        and fa.member_id = r.member_id
    left join email as em
        on  em.campaign_id = r.campaign_id
        and em.member_id = r.member_id
    left join page as pg
        on  pg.campaign_id = r.campaign_id
        and pg.member_id = r.member_id

)

select * from final