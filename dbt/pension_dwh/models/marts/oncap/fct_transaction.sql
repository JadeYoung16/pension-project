{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        incremental_strategy='delete+insert'
    )
}}

with

-- ============================================================
-- source: 读 staging
-- incremental 时只读 look-back 窗口内的新数据 (30 天)
-- ============================================================
source as (

    select *
    from {{ ref('stg_oncap__transaction') }}

    {% if is_incremental() %}
    -- 增量 run: 只处理 pay_period_end 在 "已有数据最大日期 - 30 天" 之后的行
    -- 30 天 look-back 覆盖雇主迟到/调整的 remittance (设计文档 488 行)
    where pay_period_end >= (    -- noqa: LT02
        select dateadd('day', -30, max(pay_period_end))    -- noqa: LT02
        from {{ this }}    -- noqa: LT02
    )    -- noqa: LT02
    {% endif %}

),

-- ============================================================
-- deduped: row_number 去重
-- 生成器重复写入 3 个 transaction_id; 每组留 source_row_num 最小 (首次写入)
-- ============================================================
deduped as (

    select *
    from (
        select 
            *,
            row_number() over (
                partition by transaction_id
                order by source_row_num
            ) as rn
        from source
    ) as numbered
    where rn = 1

),

-- ============================================================
-- joined: point-in-time join 两个 SCD2 维度
-- ============================================================
joined as (

    select
        d.*,
        m.member_sk,
        e.employer_sk

    from deduped d

    left join {{ ref('dim_member') }} m
        on d.member_id = m.member_id  -- noqa: LT02
        and d.pay_period_end < coalesce(m.valid_to, '9999-12-31')

    left join {{ ref('dim_employer') }} e
        on d.employer_id = e.employer_id  -- noqa: LT02
        and d.pay_period_end < coalesce(e.valid_to, '9999-12-31')
),

-- ============================================================
-- final: 拼装事实表
-- ============================================================
final as (

    select
        -- PK (degenerate, 守 grain; 裸自然键)
        transaction_id,

        -- foreign keys → dimensions
        member_sk,
        employer_sk,
        cast(to_char(pay_period_end, 'YYYYMMDD') as integer) as event_date_sk,  -- → dim_date.date_sk

        -- degenerate dimensions (无独立维度的描述性标识)
        transaction_status,         -- 'ok' / 'rj' (rejected 留痕, 查询层过滤)
        contribution_type,          -- 'reg'
        pay_frequency,              -- 'weekly' / 'semimonthly'
        pay_period_end,             -- event-time, 也作 degenerate dim

        -- measures (全 fully-additive)
        member_contribution,
        employer_contribution,
        member_contribution + employer_contribution as total_contribution,  -- 派生
        pensionable_earnings

    from joined

)

select * from final
