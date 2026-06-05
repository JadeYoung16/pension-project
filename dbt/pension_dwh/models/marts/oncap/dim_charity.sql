with

-- ============================================================
-- 度量层: schedule3 薪酬数据 (主表, 定义 grain)
-- 13 个 CRA line 行号 → 语义化列名 (依据 Open Data Data Dictionary v2.0 p.35)
-- ============================================================
charity_compensation as (

    select
        -- keys
        business_number,
        fiscal_period_end,
        form_id,

        -- headcount (计数)
        line_300 as full_time_positions,        -- 全职带薪岗位数
        line_370 as part_time_employees,        -- 兼职/部分年度雇员数

        -- top-10 高薪职位的薪酬带分布 (计数, 单位: 人)
        line_305 as comp_band_1_40k,            -- $1–39,999
        line_310 as comp_band_40k_80k,          -- $40,000–79,999
        line_315 as comp_band_80k_120k,         -- $80,000–119,999
        line_320 as comp_band_120k_160k,        -- $120,000–159,999
        line_325 as comp_band_160k_200k,        -- $160,000–199,999
        line_330 as comp_band_200k_250k,        -- $200,000–249,999
        line_335 as comp_band_250k_300k,        -- $250,000–299,999
        line_340 as comp_band_300k_350k,        -- $300,000–349,999
        line_345 as comp_band_350k_plus,        -- $350,000+

        -- compensation expenditure (金额, 单位: CAD)
        line_380 as part_time_comp_total,       -- 兼职薪酬总支出
        line_390 as total_comp_expenditure      -- 全部薪酬总支出

    from {{ ref('stg_external__t3010_schedule3') }}

),

-- ============================================================
-- 身份层: ident 机构身份/地址/分类
-- category 留 code, label 后面 join seed 补
-- ============================================================
charity_identity as (

    select
        business_number,
        legal_name,
        account_name,
        city,
        province,
        ltrim(category, '0') as sector_category_code   -- '0030' → '30', 对齐 seed 的 integer code
    from {{ ref('stg_external__t3010_ident') }}

),

-- ============================================================
-- 组装层: 薪酬(主) LEFT JOIN 身份 LEFT JOIN sector seed
-- 现算 PK 和 fiscal_year
-- ============================================================
joined as (

    select
        -- surrogate key (代理键)
        {{ dbt_utils.generate_surrogate_key(['c.business_number', 'c.fiscal_period_end']) }} as charity_sk,

        -- natural keys
        c.business_number,
        c.fiscal_period_end,
        left(c.fiscal_period_end, 4) as fiscal_year,    -- yearly partition 分区键
        c.form_id,

        -- identity attributes (from ident)
        i.legal_name,
        i.account_name,
        i.city,
        i.province,

        -- sector (code + label, 复用 employer 同款 seed)
        i.sector_category_code,
        s.sector_category_label as sector_category,

        -- compensation measures (headcount)
        c.full_time_positions,
        c.part_time_employees,

        -- compensation bands
        c.comp_band_1_40k,
        c.comp_band_40k_80k,
        c.comp_band_80k_120k,
        c.comp_band_120k_160k,
        c.comp_band_160k_200k,
        c.comp_band_200k_250k,
        c.comp_band_250k_300k,
        c.comp_band_300k_350k,
        c.comp_band_350k_plus,

        -- compensation expenditure
        c.part_time_comp_total,
        c.total_comp_expenditure

    from charity_compensation c
    left join charity_identity i
        on c.business_number = i.business_number
    left join {{ ref('cra_sector_category') }} s
        on i.sector_category_code = s.sector_category_code

)

select * from joined