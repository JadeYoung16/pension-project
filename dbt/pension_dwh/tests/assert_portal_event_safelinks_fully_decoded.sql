-- Decoding only handles known escapes; any '%' left
-- means a new escape needs a replace() rule
select event_id, safelinks_target_url
from {{ ref('stg_oncap__portal_event') }}
where contains(safelinks_target_url, '%')