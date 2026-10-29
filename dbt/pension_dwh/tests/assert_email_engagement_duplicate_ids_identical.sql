-- Staging dedup keeps one copy per event_id. This is only safe if duplicate
-- copies are identical. Fails if any event_id has copies with different
-- business content (correction event or ID collision) → investigate.
-- Note: if the ESP adds a column, add it to the HASH below.
{{ config(severity = 'error') }}

select
    event_id,
    count(*) as n_copies
from {{ source('raw_oncap', 'email_engagement') }}
group by event_id
having count(distinct hash(
    member_id, campaign_id, campaign_name, event_type,
    event_timestamp, link_url_clicked, bounce_type
)) > 1