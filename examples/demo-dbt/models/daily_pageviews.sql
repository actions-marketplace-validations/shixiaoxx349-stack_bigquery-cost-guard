-- Good version: one day of English Wikipedia pageviews.
-- The datehour partition filter keeps the scan small — this is the Before state.
select
    title,
    sum(views) as views
from `bigquery-public-data.wikipedia.pageviews_2021`
where datehour >= timestamp('2021-06-01')
  and datehour <  timestamp('2021-06-02')
  and wiki = 'en'
group by title
