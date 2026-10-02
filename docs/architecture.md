# Architecture

## Phase 1 (MVP) — runs entirely inside the customer's GitHub Actions

```text
GitHub Pull Request
        |
        v
GitHub Actions runner (ubuntu-latest, customer-owned)
        |
        |-- checkout + detect changed *.sql
        |-- dbt deps / dbt compile   (only if dbt_project.yml exists)
        |
        v
Google Cloud Workload Identity Federation
        |   (GitHub OIDC token -> short-lived GCP credential)
        v
Service Account impersonation
        |
        v
BigQuery Dry Run   (dry_run=True, NEVER executes the query)
        |
        v
Cost analysis + static SQL analysis
        |
        v
GitHub PR comment   (one comment, updated in place)
```

There is **no always-on server** and **no SaaS backend** in Phase 1. The entire
pipeline runs in the customer's own GitHub Actions minutes, against the
customer's own GCP project. Fixed infrastructure cost is therefore effectively
zero.

## Why the work runs in GitHub Actions, not in a SaaS backend

| Concern | GitHub Actions approach |
|---|---|
| **Fixed cost** | No Lambda, no compute to keep warm. $0 when no PRs are open. |
| **Credentials** | Customer GCP access never leaves their org. No SA JSON key stored anywhere. |
| **dbt compile CPU/RAM** | Paid for by the customer's runner, not our backend. |
| **Security boundary** | Stays inside the customer's GitHub organization. |
| **WIF compatibility** | GitHub OIDC -> Google WIF works natively from Actions. |

This separation is the core design principle and must not be eroded by moving
heavy work server-side.

## Component map (Phase 1)

| Module | Responsibility |
|---|---|
| `config.py` | Parse `.bq-cost-guard.yml`, apply defaults. |
| `github.py` | List changed SQL files, detect fork PRs, upsert the PR comment. |
| `dbt.py` | Run `dbt compile`, locate compiled SQL. |
| `bigquery.py` | Dry-run-only byte estimation. Never executes queries. |
| `analyzer.py` | Static SQL checks (SELECT *, CROSS JOIN, ...). |
| `report.py` | Render the Markdown PR comment. |
| `cli.py` | `analyze` (single file) and `run` (full pipeline) entry points. |
| `action.yml` | Composite GitHub Action wiring Python + WIF auth + the CLI. |

## Phase 2 (future, NOT built yet) — optional SaaS control plane

Only pursued if Phase 1 proves demand. Designed to stay serverless and cheap.

```text
GitHub App
     |
     v
Lambda Function URL        (webhook receiver, HMAC-SHA256 verified)
     |
     v
SQS Standard queue
     |
     v
Worker Lambda              (arm64, no VPC, small timeout, reserved concurrency)
     |
     v
DynamoDB                   (installation + usage metering; added only when needed)
```

Constraints that carry forward into Phase 2:

- No EC2 / ECS / Fargate / RDS / NAT Gateway / ALB.
- Lambda is never attached to a VPC.
- Secrets in SSM Parameter Store SecureString, never AWS Secrets Manager.
- No customer Service Account JSON keys are ever stored.
- CloudWatch Logs retention set to 7 days; no SQL/tokens/payloads logged.

See [roadmap.md](roadmap.md) for sequencing.
