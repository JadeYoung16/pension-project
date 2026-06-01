-- =============================================================================
-- stg_external__t3010_schedule3
-- =============================================================================
-- One row per (charity, fiscal year end) combination. CRA T3010 Schedule 3 =
-- Compensation of Employees. 43,151 rows.
--
-- Grain: composite (business_number, fpe). Most charities file once per
-- fiscal year; ~68 BNs appear multiple times due to multi-year filings.
--
-- Schedule 3 columns are CRA T3010 form line numbers (300, 305, ...).
-- Raw stored as VARCHAR (CSV has no native typing); staging casts to NUMBER.
-- Day-7 scope: minimal rename to line_NNN. Week 6 will provide semantic
-- names (e.g. line_300 -> total_compensation_positions) once T3010 form
-- spec is documented.
--
-- 1:1 mirror of raw with:
--   - cast all line_NNN columns to NUMBER (raw is VARCHAR but contains
--     numeric strings or NULL)
--   - rename "300" -> line_300 (SQL identifiers cannot start with digits)
--   - preserve sparse NULL pattern (small charities don't report all lines)
--
-- Known issues:
--   - 8 BNs in schedule3 are not in t3010_ident (orphan, 0.02%) — likely
--     CRA data sync timing. Relationships test configured as warn.
--   - line_300 is 15.8% NULL (6,829 rows) — many small charities have
--     zero employees, leave it blank rather than report 0
-- =============================================================================

with

source as (

    select * from {{ source('raw_external', 't3010_schedule3') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        bn                          as business_number,                      -- FK to ident
        fpe                         as fiscal_period_end,                    -- DATE-like; raw VARCHAR
        form_id,                                                             -- CRA form schedule identifier

        -- --- T3010 Schedule 3 line items (cast VARCHAR -> NUMBER) ----------
        cast("300" as number)       as line_300,
        cast("305" as number)       as line_305,
        cast("310" as number)       as line_310,
        cast("315" as number)       as line_315,
        cast("320" as number)       as line_320,
        cast("325" as number)       as line_325,
        cast("330" as number)       as line_330,
        cast("335" as number)       as line_335,
        cast("340" as number)       as line_340,
        cast("345" as number)       as line_345,
        cast("370" as number)       as line_370,
        cast("380" as number)       as line_380,
        cast("390" as number)       as line_390,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed
