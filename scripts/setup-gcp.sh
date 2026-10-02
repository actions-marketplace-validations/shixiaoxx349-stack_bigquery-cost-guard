#!/usr/bin/env bash
#
# setup-gcp.sh — Configure Google Cloud Workload Identity Federation so a GitHub
# repository can run BigQuery dry runs without a Service Account JSON key.
#
# Creates (idempotent):
#   - a Workload Identity Pool
#   - an OIDC provider trusting GitHub Actions tokens, scoped to ONE repo
#   - a Service Account with minimum IAM for dry run
#   - an IAM binding allowing that repo to impersonate the Service Account
#
# Usage:
#   ./scripts/setup-gcp.sh --project <GCP_PROJECT_ID> --repo <GITHUB_ORG/REPO> \
#       [--dataset DATASET ...] [--all-datasets]
#
# Data-read access (least privilege by default):
#   - No dataset read access is granted unless you ask for it.
#   - Public datasets (e.g. bigquery-public-data) need no grant.
#   - --dataset NAME   grant read (READER) on that dataset only; repeatable.
#   - --all-datasets   grant project-wide bigquery.dataViewer (BROAD — this role
#                      can query/export table data across the whole project).
#
# Example:
#   ./scripts/setup-gcp.sh --project my-analytics --repo acme-corp/data-models \
#       --dataset analytics --dataset staging
#
# Requirements: gcloud CLI, authenticated with IAM admin rights. python3 is used
# for --dataset grants (falls back to printed instructions if absent).
#
set -euo pipefail

PROJECT_ID=""
GITHUB_REPO=""
ALL_DATASETS=0
DATASETS=()
# The published Action this setup targets. Override with ACTION_REF=owner/repo@ref.
ACTION_REF="${ACTION_REF:-shixiaoxx349-stack/bigquery-cost-guard@v1}"

usage() {
  cat >&2 <<EOF
Usage: $0 --project <GCP_PROJECT_ID> --repo <GITHUB_ORG/REPO> [--dataset NAME ...] [--all-datasets]
Example: $0 --project my-analytics --repo acme-corp/data-models --dataset analytics
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)      PROJECT_ID="${2:-}"; shift 2 ;;
    --repo)         GITHUB_REPO="${2:-}"; shift 2 ;;
    --dataset)      DATASETS+=("${2:-}"); shift 2 ;;
    --all-datasets) ALL_DATASETS=1; shift ;;
    -h|--help)      usage ;;
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
warn() { printf '  \033[0;33m!\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m» %s\033[0m\n' "$1"; }

grant_dataset_reader() {
  local proj="$1" ds="$2" sa="$3"
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found — grant 'BigQuery Data Viewer' to serviceAccount:${sa} on ${proj}:${ds} in the Console"
    return
  fi
  local tmp; tmp="$(mktemp)"
  if ! bq show --format=prettyjson "${proj}:${ds}" >"${tmp}" 2>/dev/null; then
    warn "dataset ${proj}:${ds} not found or not accessible — skipping"
    rm -f "${tmp}"; return
  fi
  python3 - "${tmp}" "${sa}" <<'PY'
import json, sys
path, sa = sys.argv[1], sys.argv[2]
d = json.load(open(path))
access = d.setdefault("access", [])
entry = {"role": "READER", "userByEmail": sa}
if entry not in access:
    access.append(entry)
json.dump(d, open(path, "w"))
PY
  if bq update --source "${tmp}" "${proj}:${ds}" >/dev/null 2>&1; then
    ok "dataset READER on ${proj}:${ds}"
  else
    warn "failed to grant READER on ${proj}:${ds} — do it in the Console"
  fi
  rm -f "${tmp}"
}

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

step "Granting minimum IAM"
# jobUser lets the SA submit the dry-run job (bundles bigquery.jobs.create).
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" --condition=None >/dev/null
ok "roles/bigquery.jobUser (project)"

# Read access is least-privilege by default (none unless requested).
if [[ "${ALL_DATASETS}" -eq 1 ]]; then
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.dataViewer" --condition=None >/dev/null
  warn "roles/bigquery.dataViewer granted PROJECT-WIDE (broad: can read ALL datasets)"
elif [[ ${#DATASETS[@]} -gt 0 ]]; then
  for ds in "${DATASETS[@]}"; do grant_dataset_reader "${PROJECT_ID}" "${ds}" "${SA_EMAIL}"; done
else
  step "Data read access"
  echo "  No dataset read access granted (least privilege)."
  echo "  - Public datasets (e.g. bigquery-public-data) need no grant."
  echo "  - Your own datasets: re-run with --dataset NAME (repeatable)."
  echo "  - Or --all-datasets for a broad project-wide grant (not recommended)."
fi

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

 1) Add these as GitHub repository Variables on ${GITHUB_REPO}
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
            - uses: ${ACTION_REF}
              with:
                config: .bq-cost-guard.yml
                workload_identity_provider: \${{ vars.GCP_WIF_PROVIDER }}
                service_account: \${{ vars.GCP_SERVICE_ACCOUNT }}

 3) Open a Pull Request that changes a .sql file.
==========================================================================
EOF
