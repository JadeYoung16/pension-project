-- Whitelist filter in staging keeps only numeric member_id.
-- Fail if it dropped anything that isn't a blank or a summary row.
select *
from {{ source('raw_oncap', 'campaign_assignment') }}
where try_to_number(member_id) is null
  and nullif(trim(member_id), '') is not null
  and not coalesce(member_id ilike '%total%', false)