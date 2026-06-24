{{ config(materialized='table') }}

with

-- ============================================================
-- buyback_events: 筛出 buyback 状态事件 (排除 installment_pay 付款明细)
-- ============================================================
buyback_events as (

    select
        member_id,
        employer_id,
        event_type_code,
        event_date,
        buyback_category_code,
        buyback_service_years,
        payment_method,
        installment_months,
        is_within_window,
        is_open_option,
        total_cost
    from {{ ref('stg_oncap__life_event') }}
    where event_type_code ilike 'bbk%'
      and event_type_code != 'bbk_installment_pay'   -- 付款明细不是里程碑

),

-- ============================================================
-- pivoted: 多行事件 → 一行 (一个 member 一次 buyback)
-- 每个里程碑一个日期列; 链级属性用 max() 聚合 (已验证链内一致)
-- ============================================================
pivoted as (

    select
        member_id,
        max(employer_id) as employer_id,

        -- 5 个里程碑日期 (pivot)
        max(case when event_type_code = 'bbk_quote'     then event_date end) as quote_date,
        max(case when event_type_code = 'bbk_app'       then event_date end) as app_date,
        max(case when event_type_code = 'bbk_approved'  then event_date end) as approved_date,
        max(case when event_type_code = 'bbk_complete'  then event_date end) as completed_date,
        max(case when event_type_code = 'bbk_cancelled' then event_date end) as cancelled_date,

        -- 链级属性 (链内一致, max 取值)
        max(buyback_category_code)   as buyback_category,
        max(buyback_service_years)   as buyback_service_years,
        max(payment_method)          as payment_method,
        max(installment_months)      as installment_months,
        max(is_within_window)        as is_within_window,
        max(is_open_option)          as is_open_option,
        max(total_cost)              as total_cost

    from buyback_events
    group by member_id

),

-- ============================================================
-- ordered: 对齐 quote/app 顺序 (两者都有则 quote≤app; 只有一个则保留)
-- 业务: quote(报价)应早于 app(申请); 无 quote 的是"未报价直接申请"
-- ============================================================
ordered as (

    select
        * exclude (quote_date, app_date),
        case
            when quote_date is not null and app_date is not null
                then least(quote_date, app_date)
            else quote_date
        end as quote_date,
        case
            when quote_date is not null and app_date is not null
                then greatest(quote_date, app_date)
            else app_date
        end as app_date
    from pivoted

),

-- ============================================================
-- final: PK + 终态 + lag + point-in-time join 取 sk
-- ============================================================
final as (
    select
        -- PK (裸自然键, grain key; 注: 业务可多次 buyback, 未来需 buyback 实例 id)
        p.member_id,

        -- foreign keys (point-in-time range join, 用 quote_date 绑版本)
        m.member_sk,
        e.employer_sk,
        cast(to_char(p.quote_date, 'YYYYMMDD') as integer) as quote_date_sk,  -- 触达时点 → dim_date

        -- milestone dates
        p.quote_date,
        p.app_date,
        p.approved_date,
        p.completed_date,
        p.cancelled_date,

        -- outcome 终态判定 (对应漏斗各档)
        case
            when p.completed_date is not null then 'completed'
            when p.cancelled_date is not null then 'cancelled'
            when p.approved_date  is not null then 'approved_not_completed'
            when p.app_date       is not null then 'applied_not_approved'
            else 'quoted_only'
        end as outcome,

        -- lag measures (阶段耗时, 单位天; ⚠️ 可能负数, generator artifact, 待业务核实)
        datediff('day', p.quote_date,    p.app_date)       as days_quote_to_app,
        datediff('day', p.app_date,      p.approved_date)  as days_app_to_approved,
        datediff('day', p.approved_date, p.completed_date) as days_approved_to_completed,
        datediff('day', p.quote_date,    p.completed_date) as days_total_cycle,

        -- degenerate dims + measures
        p.buyback_category,
        p.payment_method,
        p.installment_months,
        p.is_within_window,
        p.is_open_option,
        p.buyback_service_years,
        p.total_cost

    from ordered p

    left join {{ ref('dim_member') }} m
        on p.member_id = m.member_id    -- noqa: LT02
        and coalesce(p.quote_date, p.app_date) < coalesce(m.valid_to, '9999-12-31')

    left join {{ ref('dim_employer') }} e
        on p.employer_id = e.employer_id    -- noqa: LT02
        and coalesce(p.quote_date, p.app_date) < coalesce(m.valid_to, '9999-12-31')

)

select * from final
