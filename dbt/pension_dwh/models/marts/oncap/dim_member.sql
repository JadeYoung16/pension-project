with snapshot_source as (

    select * from {{ ref('member_snap') }}

),

versioned as (

    -- dbt_valid_from is the snapshot run time, not
    -- when the attributes became true. Derive business
    -- dates from the census file instead.
    select
        *,
        to_date(
            regexp_substr(
                _source_file,
                '_([0-9]{8})[.]csv$',
                1, 1, 'e', 1
            ),
            'YYYYMMDD'
        ) as census_as_of_date,
        row_number() over (
            partition by member_id, employer_id
            order by dbt_valid_from
        ) as version_seq
    from snapshot_source

),

business_dated as (

    -- First version is open back to 1900 so facts
    -- older than the first census can still join.
    -- Later versions start on their census date.
    select
        *,
        iff(
            version_seq = 1,
            '1900-01-01'::timestamp_ntz,
            census_as_of_date::timestamp_ntz
        ) as business_valid_from
    from versioned

),

renamed as (

    select
        -- surrogate key (used by fact joins)
        dbt_scd_id as member_sk,

        -- natural key
        member_id,
        employer_id,

        -- PII
        first_name,
        last_name,
        dob,
        email,
        postal_code,

        -- code + label
        status_code,
        case status_code
            when 'A' then 'Active'
            when 'D' then 'Deferred'
            when 'R' then 'Retired'
            when 'T' then 'Terminated'
            when 'S' then 'Survivor'
        end as status,

        -- code + label
        sex_code,
        case sex_code
            when '1' then 'Male'
            when '2' then 'Female'
            when '9' then 'Not stated'
        end as sex,

        -- code + label
        marital_status_code,
        case marital_status_code
            when 'S' then 'Single'
            when 'M' then 'Married'
            when 'D' then 'Divorced'
            when 'W' then 'Widowed'
            when 'U' then 'Unknown'
        end as marital_status,

        -- code + label
        salary_band_code,
        case salary_band_code
            when 'EN' then 'Entry'
            when 'MD' then 'Mid'
            when 'SR' then 'Senior'
            when 'EX' then 'Executive'
        end as salary_band,

        -- dates
        enrollment_date,
        termination_date,

        -- attributes reflect this census date,
        -- not the fact's event date
        census_as_of_date,

        -- SCD2 validity on business dates
        business_valid_from as valid_from,
        lead(business_valid_from) over (
            partition by member_id, employer_id
            order by dbt_valid_from
        ) as valid_to

    from business_dated

)

select * from renamed