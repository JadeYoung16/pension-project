-- =============================================================================
-- stg_external__t3010_ident
-- =============================================================================
-- One row per CRA-registered Canadian charity (current registration roster).
-- 83,969 rows.
--
-- CRA T3010 = Canadian Charity Information Return, filed annually by all
-- registered charities. Public data, used in our project to enrich employer
-- dimension via business number (BN) join in Week 6 marts.
--
-- 1:1 mirror of raw with:
--   - preserve all fields (no rename, no cast) — raw schema is already
--     CRA's official format
--   - no case normalization on category/sub_category — values are CRA
--     codes (numeric strings), some legacy "0030" format coexists with
--     "30"; normalization deferred to mart layer (dim_charity_category lookup)
--
-- Notable:
--   - country is 99.96% 'CA' (Canadian); 34 'US' and 2 'GB' (cross-border)
--   - 2 rows have NULL province (CRA data gap)
--   - dual-format category codes (0030 + 30) is upstream artifact, see
--     yaml description
-- =============================================================================

with

source as (

    select * from {{ source('raw_external', 't3010_ident') }}

),

renamed as (

    select

        -- --- identifier ----------------------------------------------------
        bn                                                          as business_number,

        -- --- classification (CRA codes, normalize leading zeros) -----------
        ltrim(category, '0')        as category,                     -- '0030' -> '30'
        ltrim(sub_category, '0')    as sub_category,                 -- 同 normalization
        designation,                                                 -- A/B/C, preserved

        -- --- names (display, C-class) --------------------------------------
        legal_name,
        account_name,

        -- --- address (display, C-class) ------------------------------------
        address_line_1,
        address_line_2,
        city,
        province,                                                    -- mostly ON/QC/BC; some US states
        postal_code,
        country,                                                     -- mostly CA; 34 US + 2 GB

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed