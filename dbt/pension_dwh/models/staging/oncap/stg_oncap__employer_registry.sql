-- =============================================================================
-- stg_oncap__employer_registry
-- =============================================================================
-- One row per employer (plan sponsor). 400 rows. 1:1 mirror of raw with:
--   - rename for downstream clarity (status → employer_status, etc.)
--   - lowercase normalization on enum text columns
--   - map cryptic pay_frequency codes (mo/sm/bw/wk) to human-readable values
--   - cast nothing (raw types already correct: DATE/NUMBER/VARCHAR)
--
-- ---------------------------------------------------------------------------
-- Case normalization principle (applied consistently across stg_oncap_*):
--   A. Enum text (closed value set, used in WHERE/GROUP BY): lower()
--      Subcase A': cryptic short codes (e.g. 'mo' for monthly):
--                  map to human-readable in case-statement
--      e.g. pay_frequency: mo→monthly, sm→semimonthly, bw→biweekly, wk→weekly
--   B. Numeric-coded enum: preserve (lower is a no-op)
--      e.g. sector_category_code, business_number, postal_code
--   C. Display-bound free text: preserve original case
--      e.g. legal_name, administrator_name, city
--
-- Upstream context:
--   employer_generator.py phase-1 ships pay_frequency/status/size_band UPPERCASE.
--   phase-2 (Week 4 Day 1) ships acquisition_channel/prospect_source lowercase.
--   pay_frequency uses 2-letter codes mirroring real pension admin systems;
--   we expand to full names here so downstream marts don't carry the lookup.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'employer_registry') }}

),

renamed as (

    select

        -- --- identifiers (numeric-coded, preserved) ------------------------
        employer_id,
        business_number,

        -- --- names (display-bound, preserved) ------------------------------
        legal_name              as employer_legal_name,
        operating_name          as employer_operating_name,

        -- --- classification (enum normalized) ------------------------------
        sector_category_code,                              -- B: numeric code

        lower(employer_size_band)  as size_band,           -- A: UPPER→lower

        -- A': map 2-letter code to full word
        case lower(pay_frequency)
            when 'wk' then 'weekly'
            when 'bw' then 'biweekly'
            when 'sm' then 'semimonthly'
            when 'mo' then 'monthly'
        end                        as pay_frequency,

        lower(status)              as employer_status,     -- A: UPPER→lower

        -- --- location (preserved) ------------------------------------------
        city,                                              -- C: display
        postal_code,                                       -- B: Canada postal

        -- --- size metrics --------------------------------------------------
        employee_count,
        enrolled_member_count,

        -- --- lifecycle -----------------------------------------------------
        participation_start_date,

        -- --- admin contact (preserved) -------------------------------------
        plan_administrator_name   as administrator_name,   -- C: display
        plan_administrator_email  as administrator_email,  -- already lower

        -- --- acquisition (Week 4 Day 1; already lowercase) -----------------
        acquisition_channel,                               -- A: already lower
        prospect_source,                                   -- A: already lower
        first_contact_date,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed