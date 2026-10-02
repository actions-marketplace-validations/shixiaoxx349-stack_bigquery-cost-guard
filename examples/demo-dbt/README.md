# Demo dbt project — produce a real PR screenshot

Minimal dbt project whose only purpose is to make Cost Guard produce a clear
**Before/After** comment you can screenshot for the README / Marketplace listing.
No new product features; two tiny models; no `on-run-start` / `on-run-end` /
`run_query()`.

Reading time: ~5–10 minutes.

## What it demonstrates

- `models/daily_pageviews.sql` — one day of English Wikipedia pageviews
  (partition-filtered → small scan). This is the **Before**.
- `models/enwiki_hourly.sql` — a second small model, so the comment table shows a
  healthy ✅ row too.
- `regression_example.sql` — the **After**: partition filter removed + `SELECT *`.
  Paste it into `daily_pageviews.sql` in a PR to trigger a big Before/After jump
  and a `SELECT *` finding.

## 0. Verify the public dataset first (do this before anything else)

This demo reads `bigquery-public-data.wikipedia.pageviews_2021`. Public datasets
occasionally change, so confirm it exists and is queryable from your project:

```bash
# Lists the table if it exists (uses your gcloud/bq auth):
bq show bigquery-public-data:wikipedia.pageviews_2021

# Or a zero-cost dry run of the demo query:
bq query --use_legacy_sql=false --dry_run \
'select title, sum(views) views
 from `bigquery-public-data.wikipedia.pageviews_2021`
 where datehour >= timestamp("2021-06-01") and datehour < timestamp("2021-06-02")
   and wiki = "en" group by title'
```

If it is **not** available, swap to a fallback (both are large, date-partitioned,
and actively maintained) and update the three `.sql` files accordingly:

- `bigquery-public-data.wikipedia.pageviews_2020` (same schema: `datehour`, `wiki`, `title`, `views`)
- `bigquery-public-data.crypto_ethereum.transactions` (partitioned by `block_timestamp`; filter `where block_timestamp >= '2022-01-01' and block_timestamp < '2022-01-02'`)

> Note: this project could not be live-verified by the author (offline, no BigQuery
> credentials). The dry-run above is the authoritative check — run it first.

## 1. Create a demo repo from this folder

Use **this folder as the repo root** (so `dbt_project.yml`, `profiles.yml`, and
`.bq-cost-guard.yml` sit at the top level):

```bash
cp -r examples/demo-dbt /tmp/cost-guard-demo && cd /tmp/cost-guard-demo
mkdir -p .github/workflows
cp github-workflow.yml .github/workflows/bq-cost-guard.yml
git init -b main && git add -A && git commit -m "demo: good baseline"
# create an empty GitHub repo, then:
# git remote add origin https://github.com/<you>/cost-guard-demo.git && git push -u origin main
```

Edit two placeholders first:
- `.bq-cost-guard.yml` → set `bigquery.project_id` to your GCP project.
- `.github/workflows/bq-cost-guard.yml` → set the `uses:` line to your cost-guard
  repo (e.g. `uses: <you>/bigquery-cost-guard@main` before you publish a tag).

## 2. Configure Google WIF (reuse the main script — no demo-specific auth)

```bash
# from the bigquery-cost-guard repo:
./scripts/setup-gcp.sh --project <your-gcp-project> --repo <you>/cost-guard-demo
```

Add the printed `GCP_WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` as **repository
Variables** on the demo repo (Settings → Secrets and variables → Actions →
Variables).

## 3. Open the regression PR and screenshot the comment

```bash
git checkout -b cost-regression
cp regression_example.sql models/daily_pageviews.sql
git commit -am "demo: remove partition filter + SELECT *"
git push -u origin cost-regression
# open the PR on GitHub
```

The Action runs and posts a single comment: `daily_pageviews` jumps from one day
to the whole year (large Before/After + `SELECT *` finding), while `enwiki_hourly`
stays ✅. Screenshot that comment.

**Save the screenshot to `docs/images/pr-comment.png`** in the main
bigquery-cost-guard repo — the README hero references that path.

## Notes

- Cost Guard dry-runs only; it does not execute these queries. (`dbt compile`
  itself can run hooks/macros in other projects — this demo intentionally uses
  none. See `docs/security.md`.)
- Exact byte sizes vary with the dataset; the **percentage increase** (one day →
  whole year) is what reliably trips the thresholds.
