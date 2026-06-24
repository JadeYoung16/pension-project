{{
    config(
        materialized='incremental',
        unique_key='event_id',
        incremental_strategy='delete+insert'
    )
}}

with

-- ============================================================
-- source: 读 staging
-- incremental 时只读 look-back 窗口内的新数据 (7 天)
-- portal 事件时间确定 (无雇主 remittance 那种迟到), 短窗口足够覆盖跨 run 边界的重叠
-- ============================================================
source as (

    select *
    from {{ ref('stg_oncap__portal_event') }}

    {% if is_incremental() %}
    -- 增量 run: 只处理 event_timestamp 在 "已有数据最大时间 - 7 天" 之后的行
    where event_timestamp >= (    -- noqa: LT02
        select dateadd('day', -7, max(event_timestamp))    -- noqa: LT02
        from {{ this }}    -- noqa: LT02
    )    -- noqa: LT02
    {% endif %}

),

-- ============================================================
-- joined: point-in-time join 单个 SCD2 维度 (dim_member)
-- portal 是 member 中心 (成员自身的数字行为), 无 employer 关联, 故只 join dim_member。
-- ⚠️ 技术债: 同 fct_transaction / fct_email —— snapshot check 策略致 valid_from = 系统时间(2026),
--    早于所有事件日期(2023-24)。当前维度均单版本(valid_to 全 NULL), 放宽下界,
--    仅用 valid_to 判定。多版本出现时须恢复 `event_timestamp >= valid_from` 下界
--    (见 _marts_design.md 技术债条目)。
-- ============================================================
joined as (

    select
        s.*,
        m.member_sk

    from source s

    left join {{ ref('dim_member') }} m
        on s.member_id = m.member_id
        and s.event_timestamp < coalesce(m.valid_to, '9999-12-31')  -- noqa: LT02

),

-- ============================================================
-- final: 拼装事实表 (factless —— 无 additive measure, 聚合在 query 层 count(*))
-- ============================================================
final as (

    select
        -- PK (degenerate, 守 grain; 裸自然键, event_id 待验唯一)
        event_id,

        -- foreign keys → dimensions
        member_sk,
        cast(to_char(event_timestamp, 'YYYYMMDD') as integer) as event_date_sk,  -- → dim_date.date_sk

        -- degenerate dimensions (无独立维度的描述性标识)
        event_type,                 -- 8 类: portal_login/logout, statement_view, document_download,
                                    -- pension_calculator_use, buyback_info_page_view,
                                    -- buyback_quote_request, beneficiary_page_view
        session_id,                 -- portal 特有: 一次会话标识, 支持 session 级行为分析
        page_path,                  -- 与 event_type 近 1:1 映射 (见 _marts_design.md), 保留为原始 DD,
                                    -- 分析优先用 event_type
        event_timestamp,            -- event-time, 也作 degenerate dim

        -- 派生 degenerate dim: 从 user_agent 解析设备类型
        case
            when user_agent ilike '%iphone%' or user_agent ilike '%ipad%' then 'Mobile-iOS'
            when user_agent ilike '%android%' then 'Mobile-Android'
            else 'Desktop'
        end as device_type,

        -- audit / lineage
        source_file,
        source_row_num

    from joined

)

select * from final
