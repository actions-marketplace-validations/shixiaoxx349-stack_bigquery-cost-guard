#!/usr/bin/env bash
#
# setup-gcp.sh — Configure Google Cloud Workload Identity Federation so a GitHub
# repository can run BigQuery dry runs without a Service Account JSON key.
#
# Creates (idempotent):
#   - a Workload Identity Pool
#   - an OIDC provider trusting GitHub Actions tokens, scoped to ONE repo
#   - a Service Account with the MINIMUM read-only IAM for dry run
#   - an IAM binding allowing that repo to impersonate the Service Account
#
# Usage:
#   ./scripts/setup-gcp.sh --project <GCP_PROJECT_ID> --repo <GITHUB_ORG/REPO>
#
# Example:
#   ./scripts/setup-gcp.sh --project my-analytics --repo acme-corp/data-models
#
# Requirements: gcloud CLI, authenticated as a user with IAM admin rights.
#
set -euo pipefail

PROJECT_ID=""
GITHUB_REPO=""

usage() {
  echo "Usage: $0 --project <GCP_PROJECT_ID> --repo <GITHUB_ORG/REPO>" >&2
  echo "Example: $0 --project my-analytics --repo acme-corp/data-models" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="${2:-}"; shift 2 ;;
    --repo)    GITHUB_REPO="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -z "${PROJECT_ID}" || -z "${GITHUB_REPO}" ]] && usage
if [[ "${GITHUB_REPO}" != */* ]]; then
  echo "Error: --repo must be in the form ORG/REPO (got '${GITHUB_REPO}')" >&2
  exit 1
fi

POOL_ID="github-pool"
PROVIDER_ID="github-provider"
SA_NAME="bq-cost-guard"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

ok()   { printf '  \033[0;32m✓\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m» %s\033[0m\n' "$1"; }

step "Resolving project ${PROJECT_ID}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
ok "project number: ${PROJECT_NUMBER}"
ok "trusting GitHub repo: ${GITHUB_REPO}"

step "Enabling required APIs"
gcloud services enable \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  bigquery.googleapis.com \
  --project "${PROJECT_ID}" >/dev/null
ok "APIs enabled"

step "Creating Workload Identity Pool"
gcloud iam workload-identity-pools create "${POOL_ID}" \
  --project="${PROJECT_ID}" --location="global" \
  --display-name="GitHub Actions Pool" >/dev/null 2>&1 \
  && ok "pool created" || ok "pool already exists"

step "Creating OIDC provider (restricted to ${GITHUB_REPO})"
# attribute-condition pins the provider to exactly one repository so no other
# repo (or fork) can mint tokens that impersonate the service account.
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
  --project="${PROJECT_ID}" --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" >/dev/null 2>&1 \
  && ok "provider created" || ok "provider already exists"

step "Creating service account"
gcloud iam service-accounts create "${SA_NAME}" \
  --project="${PROJECT_ID}" \
  --display-name="BigQuery Cost Guard (dry run only)" >/dev/null 2>&1 \
  && ok "service account created" || ok "service account already exists"

step "Granting MINIMUM read-only BigQuery IAM"
# bigquery.jobUser  -> submit the dry-run job (bundles bigquery.jobs.create)
# bigquery.dataViewer -> read table schema/partitioning for the estimate
# No write/edit role is granted.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" --condition=None >/dev/null
ok "roles/bigquery.jobUser"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataViewer" --condition=None >/dev/null
ok "roles/bigquery.dataViewer (tip: scope to specific datasets for least privilege)"

step "Allowing ${GITHUB_REPO} to impersonate the service account"
WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}"
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="${WIF_MEMBER}" >/dev/null
ok "workloadIdentityUser binding created"

PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

cat <<EOF

==========================================================================
 ✅ Setup complete.

 1) Add these as GitHub repository Variables
    (Settings → Secrets and variables → Actions → Variables):

      GCP_WIF_PROVIDER    = ${PROVIDER_RESOURCE}
      GCP_SERVICE_ACCOUNT = ${SA_EMAIL}

 2) Add .github/workflows/bq-cost-guard.yml:

      name: BigQuery Cost Guard
      on: pull_request
      permissions:
        contents: read
        pull-requests: write
        id-token: write
      jobs:
        cost-guard:
          runs-on: ubuntu-latest
          steps:
            - uses: actions/checkout@v4
              with: { fetch-depth: 0 }
            - uses: ${GITHUB_REPO%/*}/bigquery-cost-guard@v1
              with:
                config: .bq-cost-guard.yml
                workload_identity_provider: \${{ vars.GCP_WIF_PROVIDER }}
                service_account: \${{ vars.GCP_SERVICE_ACCOUNT }}

 3) Open a Pull Request that changes a .sql file.
==========================================================================
EOF
