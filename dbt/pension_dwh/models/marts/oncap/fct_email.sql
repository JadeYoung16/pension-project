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
-- email 事件时间确定 (无雇主 remittance 那种迟到), 短窗口足够覆盖跨 run 边界的重叠
-- ============================================================
source as (

    select *
    from {{ ref('stg_oncap__email_engagement') }}

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
-- email 是 member 中心, 无 employer 关联, 故只 join dim_member。
-- ============================================================
joined as (

    select
        s.*,
        m.member_sk

    from source s

    left join {{ ref('dim_member') }} m
        on s.member_id = m.member_id  -- noqa: LT02
        and s.event_timestamp >= m.valid_from
        and s.event_timestamp < coalesce(m.valid_to, '9999-12-31')  -- noqa: LT02

),

-- ============================================================
-- final: 拼装事实表
-- ============================================================
final as (

    select
        -- PK (degenerate, 守 grain; 裸自然键, 去重在上游 stg_oncap__email_engagement 完成)
        event_id,

        -- foreign keys → dimensions
        member_sk,
        cast(to_char(event_timestamp, 'YYYYMMDD') as integer) as event_date_sk,  -- → dim_date.date_sk

        -- degenerate dimensions (无独立维度的描述性标识)
        event_type,                 -- sent/delivered/opened/clicked/bounced/unsubscribed
        bounce_type,                -- hard/soft/unknown, bounced only; pre-2023-09 all unknown (see yml)
        campaign_id,                -- low cardinality (4), no dim_campaign
        campaign_name,              -- 与 campaign_id 成对
        link_url_clicked,           -- 仅 clicked 事件非空
        event_timestamp,            -- event-time, 也作 degenerate dim
    
        -- audit / lineage
        source_file,
        source_row_num

    from joined

)

select * from final
