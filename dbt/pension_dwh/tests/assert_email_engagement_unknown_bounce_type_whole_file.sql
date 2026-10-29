-- 'unknown' should only come from files with no bounce classification at all.
-- A file mixing 'unknown' with real types means a classified bounce lost its
-- type and was silently labelled 'unknown'.
select
    source_file,
    count_if(bounce_type = 'unknown')  as n_unknown,
    count_if(bounce_type <> 'unknown') as n_classified
from {{ ref('stg_oncap__email_engagement') }}
where event_type = 'bounced'
group by source_file
having n_unknown > 0 and n_classified > 0