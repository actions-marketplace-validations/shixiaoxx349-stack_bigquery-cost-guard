# Publish runbook (screenshot → Marketplace)

Execution steps for the user. The assistant does not run these (they need your
GitHub/GCP credentials, and push/publish are out of its scope). WSL currently has
only `git` — `gcloud`/`gh`/`dbt` are not installed, so the one `gcloud` step uses
**Google Cloud Shell** (browser, pre-authenticated, nothing to install).

Placeholders: `<you>` = your GitHub account (your git config shows
`shixiaoxx349-stack`). Personal GCP project: `bq-cost-guard-dev` (no org).

## Phase 0 — one-time prerequisites
- GitHub push auth in WSL: create a Personal Access Token (classic, `repo` scope)
  or add an SSH key. HTTPS push will prompt for it.
- Link a **billing account** to `bq-cost-guard-dev` (free tier; dry-run-only keeps
  it ~$0). Console → Billing. (If `setup-gcp.sh` errors enabling APIs, this is why.)

## Phase 1 — push the main repo (public)
Marketplace and cross-repo Action use both need it public.
1. On github.com, create an **empty public** repo `bigquery-cost-guard`
   (no README/license — the repo already has them).
2. In WSL:
   ```bash
   cd ~/private/bigquery-cost-guard
   git remote add origin https://github.com/<you>/bigquery-cost-guard.git
   git push -u origin main
   ```
   *(This is the push the assistant will not do for you.)*

## Phase 2 — create the demo repo
```bash
cp -r ~/private/bigquery-cost-guard/examples/demo-dbt ~/cost-guard-demo
cd ~/cost-guard-demo
mkdir -p .github/workflows
cp github-workflow.yml .github/workflows/bq-cost-guard.yml
# edit that file: set  uses: <you>/bigquery-cost-guard@main   (use @main until a tag exists)
git init -b main && git add -A && git commit -m "demo: good baseline"
# create an empty public repo cost-guard-demo on github.com, then:
git remote add origin https://github.com/<you>/cost-guard-demo.git
git push -u origin main
```

## Phase 3 — configure WIF in Cloud Shell (no install)
Open Cloud Shell (console, top-right `>_`), then:
```bash
gcloud config set project bq-cost-guard-dev
git clone https://github.com/<you>/bigquery-cost-guard.git
cd bigquery-cost-guard
bash scripts/setup-gcp.sh --project bq-cost-guard-dev --repo <you>/cost-guard-demo
```
Copy the printed `GCP_WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT`.

## Phase 4 — verify the public dataset (Cloud Shell)
```bash
bq query --use_legacy_sql=false --dry_run \
'select title, sum(views) views
 from `bigquery-public-data.wikipedia.pageviews_2021`
 where datehour >= timestamp("2021-06-01") and datehour < timestamp("2021-06-02")
   and wiki = "en" group by title'
```
If it fails, switch the 3 demo `.sql` files to a fallback (see
`examples/demo-dbt/README.md`).

## Phase 5 — set demo repo Variables
cost-guard-demo → Settings → Secrets and variables → Actions → **Variables**:
- `GCP_WIF_PROVIDER` = (from Phase 3)
- `GCP_SERVICE_ACCOUNT` = (from Phase 3)

## Phase 6 — open the regression PR and screenshot
```bash
cd ~/cost-guard-demo
git checkout -b cost-regression
cp regression_example.sql models/daily_pageviews.sql
git commit -am "demo: widen date range + SELECT *"
git push -u origin cost-regression
# open the PR on github.com; wait for the Action; screenshot the Cost Guard comment
```

## Phase 7 — save the screenshot
```bash
# save the image as docs/images/pr-comment.png in the main repo, then:
cd ~/private/bigquery-cost-guard
git add docs/images/pr-comment.png
git commit -m "docs: add real PR comment screenshot"
# embed it in the README hero (replace the TODO comment), then push
git push
```

## Phase 8 — release + Marketplace (after the screenshot looks good)
```bash
cd ~/private/bigquery-cost-guard
git tag v1.0.0 && git tag v1 && git push origin v1.0.0 v1
```
Then on github.com: Releases → Draft a new release from `v1.0.0` → check
**Publish this Action to the GitHub Marketplace** → pick categories (Code quality,
Continuous integration) → publish. Listing copy is in `docs/launch.md`.

## Phase 9 — launch posts, then stop coding
Post the drafts in `docs/launch.md` (Show HN / r/dataengineering / dbt Slack / X /
Zenn). Then watch the funnel (`docs/launch.md`) — write no more code until the
signal is in.
