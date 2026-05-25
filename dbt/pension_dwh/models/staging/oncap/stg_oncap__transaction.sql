-- =============================================================================
-- stg_oncap__transaction
-- =============================================================================
-- One row per pension contribution transaction. 186,865 rows.
--
-- 1:1 mirror of raw with:
--   - lowercase normalization on enum text columns
--   - pay_frequency_code mapped to readable values (WK/BW/SM/MO ->
--     weekly/biweekly/semimonthly/monthly), matching stg_oncap__employer_registry.
--     Potential macro candidate (Week 5+ DRY refactor).
--   - preserve contribution amounts (numeric)
--   - cast nothing (raw types already correct)
--
-- Known data quality issues (caught by dbt test, see _properties.yml):
--   1. transaction_id has 3 duplicates (186,862 unique of 186,865).
--      Generator bug: same transaction_id used for 2 records with
--      different pensionable_earnings. unique test configured as
--      warn (severity=warn, error_if >= 10) rather than blocking error.
--      Fix in Week 9 polish backlog.
--
--   2. contribution_type has only 1 value ('REG') in current data.
--      Generator does not produce BBK/VOL contribution types.
--      Lifecycle gap: life_event has 8,254 BBK_INSTALLMENT_PAY events
--      but no corresponding BBK transactions. Week 9 polish.
--
--   3. buyback_reference_id is 100% NULL.
--      Related to #2 — no buyback transactions to reference. Column
--      preserved for schema fidelity; relationships test omitted.

--    4. pay_period_start is 2% NULL (3,759 rows, random across all pay
--      frequencies). Generator artifact, not business design. Derivable
--      in mart layer; staging configured to warn. Week 9 generator fix.
--
-- T (trailer) rows from upstream files were skipped at COPY INTO time
-- (ON_ERROR=CONTINUE in Day 5 loader); raw layer contains only detail rows.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'transaction') }}

),

renamed as (

    select

        -- --- identifiers ---------------------------------------------------
        transaction_id,
        member_id,                                                   -- FK
        employer_id,                                                 -- FK

        -- --- pay period ----------------------------------------------------
        pay_date,
        pay_period_start,
        pay_period_end,

        -- --- pay frequency (A': map 2-letter code to full word) ------------
        case pay_frequency_code
            when 'WK' then 'weekly'
            when 'BW' then 'biweekly'
            when 'SM' then 'semimonthly'
            when 'MO' then 'monthly'
        end                          as pay_frequency,

        -- --- contribution amounts ------------------------------------------
        pensionable_earnings,
        member_contribution,
        employer_contribution,

        -- --- contribution metadata (A: lower) ------------------------------
        lower(contribution_type)     as contribution_type,

        -- --- buyback reference (currently 100% NULL; see header) -----------
        buyback_reference_id,

        -- --- transaction status (A: lower) ---------------------------------
        lower(transaction_status)    as transaction_status,

        -- --- audit pass-through --------------------------------------------
        _source_file        as source_file,
        _row_num            as source_row_num,
        _loaded_at          as loaded_at

    from source

)

select * from renamed