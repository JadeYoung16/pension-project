-- clicked events must have a link; all other events must not.
select event_id, event_type, link_url_clicked
from {{ ref('stg_oncap__email_engagement') }}
where (event_type =  'clicked' and link_url_clicked is null)
   or (event_type <> 'clicked' and link_url_clicked is not null)