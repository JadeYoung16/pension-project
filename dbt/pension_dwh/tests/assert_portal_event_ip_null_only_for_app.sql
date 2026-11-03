-- ip_hash is NULL if and only if the event is from
-- the mobile app
select event_id, user_agent, ip_hash
from {{ ref('stg_oncap__portal_event') }}
where (ip_hash is null)
   <> (user_agent ilike '%oncapmobile%')