-- =============================================================================
-- dim_salary_history
-- =============================================================================
-- SCD2 dimension: effective-dated annual salary history per membership.
-- Grain = one row per (member_id, employer_id, effective_date) — i.e. one
-- salary version per membership per change.
--
-- SCD2 is built by WINDOW-FUNCTION RANGING, not a dbt snapshot. The source
-- (employer-portal feed) already carries complete effective-dated history
-- (multiple rows per membership, each with its own effective_date), so the
-- correct mechanism is to range the pre-existing history with lead(), NOT to
-- diff successive state-snapshots. valid_from is the real business
-- effective_date (not a run timestamp), which avoids the NULL-surrogate-key
-- tech debt of the check-strategy snapshot dimensions. The model is a pure
-- idempotent full recompute: re-runnable in CI, independent of run cadence.
--
-- Data quality handling:
--   - orphan member_id (absent from member_census): EXCLUDED via semi-join
--     (referential-integrity failure → must not enter the dimension).
--   - duplicate reports (same natural key, differing reported_at): DEDUPED,
--     keeping the latest reported_at (the corrected resubmission).
--   - negative annual_salary (payroll reversal, change_reason='correction'):
--     KEPT — a legitimate business event, a normal version in the SCD2 chain.
--   - NULL annual_salary (missing report): KEPT — valid membership/date, only
--     the measure is absent; flagged by test, used via coalesce downstream.
-- =============================================================================

with

salary as (

    select * from {{ ref('stg_oncap__salary_history') }}

),

-- valid memberships only: drop orphans whose (member_id, employer_id) pair
-- is absent from census. Composite — member_id alone is not globally unique
-- (employer-scoped), so a real member_id under the wrong employer is still
-- an orphan and must be caught.
valid_memberships as (

    select distinct 
        member_id, 
        employer_id
    from {{ ref('stg_oncap__member_census') }}

),

filtered as (

    select s.*
    from salary as s
    where exists (
        select 1
        from valid_memberships as v  
        where v.member_id = s.member_id
          and v.employer_id = s.employer_id
    )

),

-- dedup duplicate reports: one row per natural key, keep latest reported_at.
deduped as (

    select *
    from filtered
    qualify row_number() over (
        partition by member_id, employer_id, effective_date
        order by reported_at desc
    ) = 1

),

-- SCD2 ranging: valid_to = next effective_date for this membership.
ranged as (

    select
        member_id,
        employer_id,
        effective_date,
        annual_salary,
        change_reason,
        reported_at,
        effective_date as valid_from,
        lead(effective_date) over (
            partition by member_id, employer_id
            order by effective_date
        ) as valid_to

    from deduped

),

final as (

    select
        -- surrogate key (grain = member_id + employer_id + effective_date)
        {{ dbt_utils.generate_surrogate_key(['member_id', 'employer_id', 'effective_date']) }} as salary_sk,    

        -- natural key
        member_id,
        employer_id,

        -- measure (dirty values preserved; flagged by test, not mutated)
        annual_salary,

        -- change reason (already lower() in staging)
        change_reason,

        -- business effective date (immutable source fact; equals valid_from
        -- numerically but kept separate: effective_date is the reported
        -- business event, valid_from is the derived SCD2 interval start)
        valid_from as effective_date,

        -- SCD2 validity window  [valid_from, valid_to)  left-closed right-open
        valid_from,
        valid_to,
        (valid_to is null) as is_current,

        -- report timestamp (audit / backdated analysis)
        reported_at

    from ranged

)

select * from final
