with snapshot_source as (

    select * from {{ ref('employer_snap') }}

),

renamed as (

    select
        -- surrogate key (代理键, fact 表 join 用)
        dbt_scd_id as employer_sk,

        -- natural key
        employer_id,

        -- external identifier (CRA business number)
        business_number,

        -- names (display)
        legal_name,
        operating_name,

        -- address
        city,
        postal_code,

        -- sector (CRA T3010 编码, 外键 → dim_sector, Day 4 解析 label)
        sector_category_code,

        -- self-describing labels (status/size 原始即全词, 无需翻译)
        status,
        employer_size_band,
        -- pay_frequency: 原始为 2 字母 code, 复用 macro 翻译 (snapshot 绕过 staging, 此处补译)
        pay_frequency as pay_frequency_code,
        {{ pay_frequency_label('pay_frequency') }} as pay_frequency,

        -- acquisition funnel labels
        acquisition_channel,
        prospect_source,

        -- counts
        employee_count,
        enrolled_member_count,

        -- dates
        participation_start_date,
        first_contact_date,

        -- plan administrator (PII)
        plan_administrator_name,
        plan_administrator_email,

        -- SCD2 有效期 (snapshot 自动列改名)
        dbt_valid_from as valid_from,
        dbt_valid_to as valid_to

    from snapshot_source

),

with_sector_label as (

    select
        r.*,
        -- sector label (lookup from seed; left join 保留无匹配/NULL code 的行)
        s.sector_category_label as sector_category

    from renamed r
    left join {{ ref('cra_sector_category') }} s
        on r.sector_category_code = s.sector_category_code

)

select * from with_sector_label
