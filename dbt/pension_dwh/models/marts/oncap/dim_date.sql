with date_spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="'2015-01-01'",
        end_date="'2036-01-01'"
    ) }}

),

calendar as (

    select cast(date_day as date) as date_value
    from date_spine

),

final as (

    select
        -- smart integer PK (YYYYMMDD) — Decision #2 MD5 例外:
        cast(to_char(date_value, 'YYYYMMDD') as integer) as date_sk,

        date_value,

        -- calendar
        year(date_value)                  as calendar_year,
        quarter(date_value)               as calendar_quarter,
        month(date_value)                 as calendar_month,
        monthname(date_value)             as month_name,
        day(date_value)                   as day_of_month,
        dayname(date_value)               as day_name,
        weekofyear(date_value)            as iso_week,
        (dayofweekiso(date_value) >= 6)   as is_weekend,   -- ISO: 6=Sat,7=Sun,与 locale 无关

        -- Canadian fiscal year (Apr 1 – Mar 31)
        case
            when month(date_value) >= 4 then year(date_value)
            else year(date_value) - 1
        end                               as fiscal_year,
        case
            when month(date_value) in (4, 5, 6)    then 1
            when month(date_value) in (7, 8, 9)    then 2
            when month(date_value) in (10, 11, 12) then 3
            else 4
        end                               as fiscal_quarter

    from calendar

)

select * from final