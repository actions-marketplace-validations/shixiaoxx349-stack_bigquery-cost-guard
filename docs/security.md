# Security Model

BigQuery PR Cost Guard is designed so that **no customer cloud credential ever
leaves the customer's own GitHub organization**, and so that **untrusted PR code
can never reach your BigQuery project**.

## 1. No long-lived GCP keys

We do **not** use Service Account JSON keys. Authentication uses
**Google Cloud Workload Identity Federation (WIF)**:

```text
GitHub Actions OIDC token
        -> Google Workload Identity Federation
        -> Service Account impersonation (short-lived token)
        -> BigQuery
```

The credential minted during a run is short-lived and scoped to a single
repository (enforced by an `attribute-condition` on the WIF provider). Nothing
is persisted. There is no key to leak, rotate, or steal.

## 2. Fork PR safety (the most important control)

PR code from a **fork** is untrusted. A malicious contributor could craft SQL or
dbt macros that attempt to exfiltrate data or abuse your GCP access.

Therefore:

- **Fork PRs never receive GCP credentials and never run a BigQuery dry run.**
  Fork detection reads `GITHUB_EVENT_PATH` (`pull_request.head.repo.fork`). When
  true, the tool runs **static analysis only** and posts a comment that says so.
- The example workflow uses the plain **`pull_request`** event. We deliberately
  do **not** use `pull_request_target`, which would run fork code with access to
  secrets — a well-known privilege-escalation footgun.
- Because `pull_request` from a fork runs without the `id-token`/secret context
  needed for WIF, the credential simply is not available to fork code even if the
  fork check were bypassed. Defense in depth.

If you want dry-run coverage for external contributions, use a maintainer
workflow that re-runs the check from a trusted branch after human review — never
grant fork code direct credential access.

### Residual same-repo risk (important)

Fork protection is **necessary but not sufficient**. Cost Guard runs
`dbt compile`, and dbt can execute real queries *during compilation*:

- `on-run-start` / `on-run-end` hooks run on `dbt compile`, not only `dbt run`.
- Macros can call `run_query(...)`, which issues a real BigQuery job.

A **same-repo branch** PR could therefore add `{% do run_query("...") %}` or a
hook that runs under your service account during compile — this is not a fork, so
the fork check does not block it. Mitigate by:

- Treating same-repo PR review as a trust boundary (require review before CI runs
  on a branch; GitHub environments / required reviewers help here).
- Keeping the service account **minimal and read-only** (`jobUser` + `dataViewer`
  only; no write/edit roles), so the blast radius is reads + query spend, not
  data mutation.
- Scoping `dataViewer` to only the datasets your models read.

## 3. Cost Guard does not execute the analyzed SQL

- Cost Guard's own BigQuery client is only ever invoked with `dry_run=True`.
- There is **no code path in Cost Guard** that executes the analyzed query or
  reads row data.
- The required IAM is scoped to submitting dry-run jobs and reading table
  metadata (schema/partitioning) — see [gcp-setup.md](gcp-setup.md).
- Caveat: this is a statement about **Cost Guard**, not about `dbt compile`, which
  is your project's code and *can* run queries (see the same-repo risk above). The
  accurate claim is "Cost Guard does not execute the analyzed SQL," not "no query
  ever runs."

## 4. What data leaves your environment

In Phase 1, **nothing leaves your GitHub + GCP environment.** The tool runs on
your runner, talks to your BigQuery, and writes a comment to your PR via the
built-in `GITHUB_TOKEN`. There is no third-party SaaS backend involved.

## 5. Secret hygiene / logging

The tool never logs:

- SQL content
- GCP tokens or credentials
- GitHub tokens
- Full webhook payloads (relevant to Phase 2)

Errors are logged by type/location to stderr, not by dumping sensitive content.

## 6. Minimum GitHub permissions

```yaml
permissions:
  contents: read         # checkout + diff
  pull-requests: write   # post/update the cost comment
  id-token: write        # mint the OIDC token for WIF
```

Grant nothing more.
