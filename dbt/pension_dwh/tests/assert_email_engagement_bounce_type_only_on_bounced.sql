-- bounced events must have a bounce_type; all other events must not.
select event_id, event_type, bounce_type
from {{ ref('stg_oncap__email_engagement') }}
where (event_type =  'bounced' and bounce_type is null)
   or (event_type <> 'bounced' and bounce_type is not null)