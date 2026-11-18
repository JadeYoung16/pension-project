with snapshot_source as (

    select * from {{ ref('employer_snap') }}

),

versioned as (

    -- dbt_valid_from is the snapshot run time, not
    -- when the attributes became true. Derive business
    -- dates from the registry file instead.
    select
        *,
        to_date(
            regexp_substr(
                _source_file,
                '_([0-9]{8})[.]csv$',
                1, 1, 'e', 1
            ),
            'YYYYMMDD'
        ) as registry_as_of_date,
        row_number() over (
            partition by employer_id
            order by dbt_valid_from
        ) as version_seq
    from snapshot_source

),

business_dated as (

    -- First version is open back to 1900 so facts
    -- older than the first registry file can still
    -- join. Later versions start on their file date.
    select
        *,
        iff(
            version_seq = 1,
            '1900-01-01'::timestamp_ntz,
            registry_as_of_date::timestamp_ntz
        ) as business_valid_from
    from versioned

),

renamed as (

    select
        -- surrogate key (used by fact joins)
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

        -- sector code (CRA T3010), label joined below
        sector_category_code,

        -- labels already full words in source
        status,
        employer_size_band,

        -- raw is a 2-letter code; snapshot reads raw,
        -- so translate here with the shared macro
        pay_frequency as pay_frequency_code,
        {{ pay_frequency_label('pay_frequency') }}
            as pay_frequency,

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

        -- attributes reflect this registry date,
        -- not the fact's event date
        registry_as_of_date,

        -- SCD2 validity on business dates
        business_valid_from as valid_from,
        lead(business_valid_from) over (
            partition by employer_id
            order by dbt_valid_from
        ) as valid_to

    from business_dated

),

with_sector_label as (

    select
        r.*,
        -- left join keeps rows with no match / NULL code
        s.sector_category_label as sector_category

    from renamed r
    left join {{ ref('cra_sector_category') }} s
        on r.sector_category_code = s.sector_category_code

)

select * from with_sector_label