# Roadmap

The guiding rule: **keep it boring, secure, cheap, and shippable.** Each phase is
built only after the previous one has proven useful. No feature is built "just in
case."

## Phase 1 — MVP (current)

Goal: a stranger can install this on a GitHub repo and see a useful BigQuery cost
comment on their Pull Requests.

- [x] Parse `.bq-cost-guard.yml` with sane defaults
- [x] Detect changed `*.sql` files in a PR
- [x] `dbt compile` integration (optional, auto-detected)
- [x] BigQuery dry run (bytes processed), dry-run-only
- [x] Static SQL analysis (SELECT *, CROSS JOIN)
- [x] Single PR comment, updated in place
- [x] Threshold-based status (warn/fail), warning-only by default
- [x] Before/After comparison with % change + optional cost line (Phase 1B)
- [x] WIF auth, no SA JSON key, fork-PR safety
- [x] Composite GitHub Action
- [x] Docs + tests

### Phase 1A vs 1B

- **1A (done):** Head-only estimate. Report the bytes the changed model would
  scan at the PR head. Reliable and simple.
- **1B (done):** Compile both base and head (base via a throwaway `git worktree`),
  dry-run each changed model on both sides, and show `Before / After / % change`.
  Increase thresholds (`warn/fail_increase_percent`) feed the status, and an
  optional on-demand cost line is shown when `pricing.price_per_tib_usd` is set.
  Falls back to head-only when the base cannot be compiled or on fork PRs.

## Phase 2 — optional SaaS control plane

Only if Phase 1 gets real usage. Stays serverless and cheap (see
[architecture.md](architecture.md)).

1. GitHub App packaging
2. GitHub Marketplace listing
3. Lambda Function URL webhook (HMAC-SHA256 verified)
4. DynamoDB for installation management
5. Usage metering
6. Free / Pro plans
7. Before/After history across PRs
8. Organization-level policy
9. Slack notification

Later still, and only if warranted: AI-generated explanations of cost
regressions. Not part of early phases.

## Explicitly NOT planned for early phases

SaaS dashboard, user/org admin UI, Stripe/Marketplace billing, AI review, Slack/
Teams/email integrations, custom OAuth/auth, RDS/Redis, analytics dashboards,
complex RBAC, mobile, i18n.
