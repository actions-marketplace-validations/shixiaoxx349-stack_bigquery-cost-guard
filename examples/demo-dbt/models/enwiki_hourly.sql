-- A second, small model (stays cheap) so the PR table shows a healthy ✅ row
-- next to the regression. Partition-pruned to a single day.
select
    datehour,
    sum(views) as views
from `bigquery-public-data.wikipedia.pageviews_2021`
where datehour >= timestamp('2021-06-01')
  and datehour <  timestamp('2021-06-02')
group by datehour
order by datehour
