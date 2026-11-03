{{ config(severity='warn') }}
-- Per file: >1% bad lines (and at least 5)
select _source_file,
       count(*) as n_rows,
       count_if(_raw_line is not null) as n_bad
from {{ source('raw_oncap', 'portal_event') }}
group by 1
having n_bad >= 5 and n_bad / n_rows > 0.01