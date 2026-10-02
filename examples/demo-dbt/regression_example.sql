-- BAD version (the regression to paste into models/daily_pageviews.sql for the PR).
-- Two problems on purpose:
--   1. the datehour range is widened from one day to the whole year -> huge scan
--      (this table requires a partition filter, so we widen the range, not remove it)
--   2. SELECT *  -> static-analysis finding + reads every column
-- Cost Guard shows a large Before/After increase (~6 GiB -> ~2 TiB) and a SELECT * finding.
select *
from `bigquery-public-data.wikipedia.pageviews_2021`
where datehour >= timestamp('2021-01-01')
  and datehour <  timestamp('2022-01-01')
  and wiki = 'en'
