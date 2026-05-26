-- =============================================================================
-- pay_frequency_label(column_name)
--
-- Maps cryptic pay-frequency codes (WK/BW/SM/MO) to human-readable values
-- ('weekly' / 'biweekly' / 'semimonthly' / 'monthly').
--
-- Defensive lower() applied inside the macro: callers don't need to know
-- whether upstream emits UPPER or lower case. Centralizes the case
-- assumption in one place — when generator behavior changes (as employer
-- did phase-1 UPPER -> phase-2 lower in Week 4 Day 1), no caller breaks.
--
-- Unknown codes return NULL (no else clause). Downstream staging models
-- should add accepted_values test on the OUTPUT column to surface any
-- new codes that need mapping.
--
-- Usage:
--   {{ pay_frequency_label('pay_frequency') }}        as pay_frequency
--   {{ pay_frequency_label('pay_frequency_code') }}   as pay_frequency
--
-- Callers (as of Week 5 Day 1):
--   - stg_oncap__employer_registry (source col: pay_frequency)
--   - stg_oncap__transaction       (source col: pay_frequency_code)
-- =============================================================================
{% macro pay_frequency_label(column_name) %}
    case lower({{ column_name }})
        when 'wk' then 'weekly'
        when 'bw' then 'biweekly'
        when 'sm' then 'semimonthly'
        when 'mo' then 'monthly'
    end
{% endmacro %}
