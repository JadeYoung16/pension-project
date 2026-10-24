-- =============================================================================
-- stg_oncap__campaign_assignment
-- =============================================================================
-- One row per member per campaign.  PK = (campaign_id, member_id).
--
-- Source delivers multiple file versions per campaign:
--   v1        = CRM export of the randomized assignment (system-generated)
--   v2_FINAL  = send list after manual Excel edits by marketing ops
--
-- Version handling (generic, not hard-coded to v1/v2):
--   - attributes (segment, arm, dates) taken from the EARLIEST version a
--     member appears in = original assignment record
--   - in_final_send_list = member appears in the LATEST version
--
-- CAMP_2023_BBK_WINDOW: 6,295 assigned, 6,219 in final list.  The 76 removed
-- members had all applied before the 2023-06-15 assignment date (verified
-- against life_event, 2026-10-22); exclusion is unrelated to arm.
--
-- Cleaning:
--   - drop non-member rows (e.g. 'Total' summary row) via whitelist:
--     member_id must be numeric (guarded by singular test)
--   - member_id: restore leading zeros stripped by Excel -> LPAD to 10
--   - dates: ISO (v1) or M/D/YYYY (v2), explicit formats, no auto-detect
--   - arm: normalize label variants to treatment / control / guardrail;
--     unknown labels pass through raw so accepted_values test shows them
--
-- Guardrail members (not randomized; always sent) are kept.  Experiment
-- analysis filters to arm in ('treatment', 'control') downstream.
-- =============================================================================

with

source as (

    select * from {{ source('raw_oncap', 'campaign_assignment') }}

),

cleaned as (

    select

        -- --- identifiers ---------------------------------------------------
        trim(campaign_id)                                       as campaign_id,
        lpad(trim(member_id), 10, '0')                          as member_id,  -- FK

        -- --- assignment ----------------------------------------------------
        lower(trim(segment))                                    as segment,
        case lower(trim(arm))
            when 'treatment'               then 'treatment'
            when 'trt'                     then 'treatment'
            when 'control'                 then 'control'
            when 'holdout'                 then 'control'
            when 'guardrail'               then 'guardrail'
            when 'guardrail - always send' then 'guardrail'
            else arm
        end                                                     as arm,

        -- --- temporal ------------------------------------------------------
        coalesce(
            try_to_date(trim(assigned_date), 'YYYY-MM-DD'),
            try_to_date(trim(assigned_date), 'MM/DD/YYYY')
        )                                                       as assigned_date,
        coalesce(
            try_to_date(trim(scheduled_send_date), 'YYYY-MM-DD'),
            try_to_date(trim(scheduled_send_date), 'MM/DD/YYYY')
        )                                                       as scheduled_send_date,

        -- --- file version (parsed from file name, e.g. _v2_FINAL_) ---------
        try_to_number(
            regexp_substr(_source_file, '_v([0-9]+)_', 1, 1, 'e', 1)
        )                                                       as source_file_version,

        -- --- audit pass-through --------------------------------------------
        _source_file                                            as source_file,
        _row_num                                                as source_row_num,
        _loaded_at                                              as loaded_at

    from source
    where try_to_number(member_id) is not null

),

latest_version as (

    select
        campaign_id,
        max(source_file_version) as latest_file_version
    from cleaned
    group by campaign_id

),

final_list_members as (

    select distinct
        c.campaign_id,
        c.member_id
    from cleaned as c
    inner join latest_version as lv
        on  c.campaign_id = lv.campaign_id
        and c.source_file_version = lv.latest_file_version

),

first_assignment as (

    select *
    from cleaned
    qualify row_number() over (
        partition by campaign_id, member_id
        order by source_file_version
    ) = 1

),

final as (

    select
        fa.campaign_id,
        fa.member_id,
        fa.segment,
        fa.arm,
        fa.assigned_date,
        fa.scheduled_send_date,
        fl.member_id is not null                                as in_final_send_list,
        fa.source_file_version,
        fa.source_file,
        fa.source_row_num,
        fa.loaded_at
    from first_assignment as fa
    left join final_list_members as fl
        on  fa.campaign_id = fl.campaign_id
        and fa.member_id = fl.member_id

)

select * from final