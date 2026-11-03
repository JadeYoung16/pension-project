-- NULL member_id is valid only on buyback_info_page_view
select event_id, event_type
from {{ ref('stg_oncap__portal_event') }}
where member_id is null
  and event_type <> 'buyback_info_page_view'