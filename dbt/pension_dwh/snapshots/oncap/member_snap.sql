{% snapshot member_snap %}

{{
    config(
        unique_key=['member_id', 'employer_id'],
        strategy='check',
        check_cols=[
            'status_code',
            'salary_band_code',
            'marital_status_code',
        ],
    )
}}

with source as (

    select * from {{ source('raw_oncap', 'member_census') }}

),

latest_snapshot as (

    select *
    from source
    where _source_file = (select max(_source_file) from source)

)

select
    member_id,
    employer_id,
    first_name,
    last_name,
    dob,
    sex_code,
    marital_status_code,
    email,
    postal_code,
    enrollment_date,
    termination_date,
    status_code,
    salary_band_code,
    _source_file,
    _row_num,
    _loaded_at
from latest_snapshot

{% endsnapshot %}