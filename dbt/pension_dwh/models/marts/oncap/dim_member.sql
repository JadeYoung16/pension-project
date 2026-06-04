with snapshot_source as (

    select * from {{ ref('member_snap') }}

),

renamed as (

    select
        -- surrogate key (代理键,fact 表 join 用)
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

        -- code + label 双留(marital_status)
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

        -- SCD2 有效期(snapshot 自动列改名)
        dbt_valid_from as valid_from,
        dbt_valid_to as valid_to

    from snapshot_source

)

select * from renamed