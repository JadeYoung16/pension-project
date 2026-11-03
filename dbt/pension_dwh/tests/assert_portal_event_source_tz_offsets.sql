{{ config(severity='warn') }}
-- Raw offsets expected: -4/-5 (Toronto) or 0 (app)
select
    extract(timezone_hour from event_timestamp) as tzh,
    extract(timezone_minute from event_timestamp)
        as tzm,
    count(*) as n
from {{ source('raw_oncap', 'portal_event') }}
where _raw_line is null
group by 1, 2
having not (tzh in (-4, -5, 0) and tzm = 0)