# Google Cloud Setup (Workload Identity Federation)

This guide configures your GCP project so a specific GitHub repository can run
**BigQuery dry runs** without any Service Account JSON key.

You can run the helper script, or follow the manual steps below.

## Option A — scripted

```bash
./scripts/setup-gcp.sh --project <GCP_PROJECT_ID> --repo <GITHUB_ORG/REPO>
# e.g.
./scripts/setup-gcp.sh --project my-analytics-project --repo acme-corp/data-models
```

It prints the two values to add to your GitHub repository variables
(`GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`).

## Option B — manual

### 1. Enable APIs

```bash
gcloud services enable \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  bigquery.googleapis.com \
  --project PROJECT_ID
```

### 2. Create a Workload Identity Pool + provider

```bash
gcloud iam workload-identity-pools create github-pool \
  --project=PROJECT_ID --location=global \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=PROJECT_ID --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='ORG/REPO'"
```

The `attribute-condition` is important: it restricts the provider to exactly one
repository so no other repo (or fork) can impersonate the service account.

### 3. Create the service account

```bash
gcloud iam service-accounts create bq-cost-guard \
  --project=PROJECT_ID \
  --display-name="BigQuery Cost Guard (dry run only)"
```

### 4. Grant MINIMUM IAM

Dry run needs to (a) submit a job and (b) resolve the tables the query reads.
Grant `jobUser` at the project level:

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:bq-cost-guard@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"          # bundles bigquery.jobs.create
```

Then grant read access **only where needed** (least privilege):

- Public datasets (e.g. `bigquery-public-data`) need **no** grant.
- For your own datasets, grant `READER` on each dataset rather than project-wide.
  The setup script does this for you via `--dataset NAME`. Manually, add an access
  entry to the dataset (Console → dataset → Sharing → Permissions, add the service
  account as *BigQuery Data Viewer*).
- `roles/bigquery.dataViewer` at the **project** level is broad — it allows the SA
  to **query and export table data across the whole project**. Only grant it
  (`--all-datasets`) if you accept that scope.

> Dry run does **not** read row data and does **not** require
> `roles/bigquery.dataEditor` or any write role. Do not grant more than the above.

### 5. Allow the repo to impersonate the SA

```bash
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')

gcloud iam service-accounts add-iam-policy-binding \
  bq-cost-guard@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/ORG/REPO"
```

### 6. Record the values for GitHub

```text
GCP_WIF_PROVIDER    = projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
GCP_SERVICE_ACCOUNT = bq-cost-guard@PROJECT_ID.iam.gserviceaccount.com
```

Add these as repository **Variables** (Settings -> Secrets and variables ->
Actions -> Variables) and reference them in the workflow `with:` block.

## Verify

Open a PR that changes a `.sql` file. The Action should authenticate via WIF,
run a dry run, and post a BigQuery Cost Guard comment. If auth fails, confirm:

- the workflow has `permissions: id-token: write`
- the `attribute-condition` repository string exactly matches `ORG/REPO`
- the provider resource name in `GCP_WIF_PROVIDER` is correct
