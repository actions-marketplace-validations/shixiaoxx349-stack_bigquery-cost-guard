-- BAD version (the regression to paste into models/daily_pageviews.sql for the PR).
-- Two problems on purpose:
--   1. the datehour partition filter is gone  -> scans the whole year, not one day
--   2. SELECT *                               -> static-analysis finding + more bytes
-- Cost Guard will show a large Before/After increase and a SELECT * warning.
select *
from `bigquery-public-data.wikipedia.pageviews_2021`
where wiki = 'en'
