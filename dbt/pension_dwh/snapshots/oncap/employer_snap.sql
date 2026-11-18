{% snapshot employer_snap %}

{{
    config(
        unique_key='employer_id',
        strategy='check',
        check_cols=[
            'status',
            'employer_size_band',
            'sector_category_code',
            'pay_frequency',
        ],
    )
}}

with source as (

    select * from {{ source('raw_oncap', 'employer_registry') }}

),

latest_snapshot as (

    select *
    from source
    where _source_file = (
        select max(_source_file) from source
    )

)

select
    employer_id,
    business_number,
    legal_name,
    operating_name,
    city,
    postal_code,
    sector_category_code,
    status,
    employer_size_band,
    pay_frequency,
    employee_count,
    enrolled_member_count,
    participation_start_date,
    plan_administrator_name,
    plan_administrator_email,
    acquisition_channel,
    prospect_source,
    first_contact_date,
    _source_file,
    _row_num,
    _loaded_at
from latest_snapshot

{% endsnapshot %}