-- page_path and event_type must map one-to-one
select 'event_type' as side, event_type as value
from {{ ref('stg_oncap__portal_event') }}
group by event_type
having count(distinct page_path) > 1

union all

select 'page_path', page_path
from {{ ref('stg_oncap__portal_event') }}
group by page_path
having count(distinct event_type) > 1