# Launch Playbook

The goal of launch week is **not** to add features. It is to publish the existing
MVP (Phase 1A + 1B, tests green) and measure whether a cold audience reacts.

**Definition of success for week one:** at least one stranger runs Cost Guard on
their own repository and a comment appears on a PR that isn't ours. Revenue is not
the week-one goal.

## Positioning

> **Catch BigQuery cost regressions in the pull request — before they hit your bill.**

- Cost Guard is a **shift-left cost lint**, not a FinOps dashboard. It stops
  high-cost SQL at review time. (Think ESLint, not Datadog.)
- It does **not** compete with production cost-observability platforms (e.g.
  SELECT, ~$1,499/mo enterprise). Different buyer, different moment.
- Differentiators (all true, all defensible): runs in CI on every PR · dry run
  only (Cost Guard never executes the analyzed SQL) · no stored GCP keys (WIF) ·
  fork-PR safe · no server, ~$0 fixed cost.

## Messaging rules

- Lead with the **incident**, not the feature. "A partition filter disappeared and
  a query jumped from 4.2 GiB to 94.7 GiB per run" beats "detects cost regressions."
- The **screenshot of a real PR comment is the hero asset.** Produce one before
  launch (see checklist).
- Say "Cost Guard does not execute the analyzed SQL" — never "no query ever runs"
  (dbt compile can run hooks/macros; see [security.md](security.md)).
- Pricing: do **not** put a number in the README yet. Say **"Free during beta;
  Team features planned."** We are validating *"would you keep this in your CI?"*,
  not $19 vs $29.

## Distribution (cold channels — no warm network required)

| Channel | Role |
|---|---|
| **GitHub Marketplace** | Required distribution surface (install target + credibility + searchable). Not a megaphone — don't expect it to push traffic on its own. |
| r/dataengineering, r/bigquery | Primary early-user source |
| dbt Community Slack (#tools-and-integrations) | Primary early-user source |
| Show HN | Initial spike |
| X (#dbt #BigQuery) | Supplementary |
| Qiita / Zenn (JP) | Supplementary, one post |

Follow each community's self-promotion rules (especially HN and Reddit).

## Metrics funnel (install count is a vanity metric)

| Stage | Signal | Question it answers |
|---|---|---|
| ① Exposure | README / post views | Did anyone see it? |
| ② Intent | Marketplace / repo visits | Were they interested? |
| ③ Setup | workflow added | Did they try to adopt? |
| ④ **Activation** | first PR comment succeeds | Could they get it working? |
| ⑤ Value | a warning fired | Did it find a real problem? |
| ⑥ **Behavior** | they changed the SQL | Did it change behavior? |
| ⑦ Retention | reused on another PR | Is there lasting value? |
| ⑧ WTP | Team-feature request / waitlist | Would they pay? |
| ⑨ Revenue | card charged | Real demand |

- The decisive segment is **④ → ⑥**. If many reach ③ but few reach ④, the problem
  is **onboarding (WIF friction)**, not the product. If many reach ④ but none reach
  ⑥, the **value** is weak. Keep these separable.
- **Time to First Comment** is a top KPI: from "found the Marketplace page" to "a
  Cost Guard comment appears on my PR." **Target: under 15 minutes.** If it takes
  30–60, invest in `scripts/setup-gcp.sh`, not features.
- Don't misread low installs in two weeks as "no demand" (cold + niche ramps
  slowly). But "views with zero intent/activation" *is* a clear negative signal.

## Validation asks (how to phrase them)

Avoid "Would you pay?" (everyone says yes). Use a needs question:

> **Which of these would you need before using Cost Guard across your team?**
> - Block merges above a cost threshold
> - Organization-wide policies
> - Repository-level budgets
> - Audit / history
> - Slack alerts
> - None — the free version is enough

Then: *"Interested in Team early access?"* → collect email / GitHub Discussion 👍.
Only after real interest, place an **Early Access $10/mo** Checkout to test true WTP
(card out). Not built this week.

## Launch-ready checklist

- [ ] Public repo (push/publish on the Mac, per ops rules)
- [ ] README hero = incident + screenshot + quick start (done; screenshot pending)
- [ ] **Real screenshot** of a PR comment at `docs/images/pr-comment.png`
- [ ] CI green badge (`.github/workflows/ci.yml` added)
- [ ] `v1.0.0` release **and** a moving `v1` tag
- [ ] Marketplace listing published (free Action)
- [ ] Early-access capture (GitHub Discussions thread or a form)
- [ ] Security wording audited (done — "Cost Guard does not execute the analyzed SQL")
- [ ] WIF onboarding dry-run: fresh project/repo → first comment under 15 min

## Execution order

1. Security wording / dbt-compile behavior audit — **done**
2. CI workflow — **done**
3. Real PR screenshot (needs a demo repo + WIF) — *Mac/human*
4. README hero polish — **done**
5. Marketplace listing copy (below) → publish — *Mac/human*
6. `v1.0.0` + `v1` release — *Mac/human*
7. Publish to GitHub Marketplace — *Mac/human*
8. Post: Show HN / Reddit / dbt Slack / X / Zenn (drafts below)
9. **Write no code. Watch the funnel.**

---

## Marketplace listing copy (draft)

- **Name:** BigQuery PR Cost Guard
- **Tagline:** Catch BigQuery cost regressions in the pull request.
- **Categories:** Code quality, Continuous integration
- **Description:**
  > BigQuery PR Cost Guard dry-runs the dbt / BigQuery SQL changed in a pull
  > request and comments the estimated bytes scanned — Before vs After, per model —
  > so cost regressions (a removed partition filter, a `SELECT *`) are caught at
  > review time instead of on the invoice. Dry run only: Cost Guard never executes
  > the analyzed SQL. Auth via GitHub OIDC → Google Workload Identity Federation;
  > no Service Account keys stored. Free during beta.

---

## Launch post drafts

### Show HN
> **Show HN: BigQuery PR Cost Guard – dry-run your dbt SQL's cost on every PR**
>
> A partition filter disappeared in one of our PRs and a query went from scanning
> 4.2 GiB to 94.7 GiB *per run* — we only noticed on the bill. So I built a GitHub
> Action that dry-runs the changed dbt/BigQuery SQL on each PR and comments the
> Before/After bytes, before merge.
>
> It's dry-run only (it never executes your SQL), auth is GitHub OIDC → Google
> Workload Identity Federation so there are no Service Account keys to store, and
> fork PRs get static analysis only (no credentials). Runs entirely in your own
> GitHub Actions — no server, no backend.
>
> Free during beta. Would love feedback on the onboarding (WIF setup) and whether
> the warnings are useful. Repo: <link>

### Reddit (r/dataengineering)
> **I built a GitHub Action that catches BigQuery cost regressions at PR time**
>
> We had a PR silently 20x a query's scan size (dropped partition filter). The bill
> told us, two weeks later. This Action dry-runs the changed dbt/BigQuery SQL on
> each PR and posts Before/After bytes + % change as a comment.
>
> - Dry run only — never executes your SQL
> - WIF auth, no stored keys; fork PRs get static analysis only
> - Runs in your Actions, ~$0, no backend
>
> It's free (beta). Honest question for this sub: is PR-time cost checking actually
> useful to you, or do your native BigQuery quotas already cover it? Repo: <link>

### dbt Community Slack (#tools-and-integrations)
> Sharing a small open-source GitHub Action: it runs `dbt compile` + BigQuery dry
> run on changed models in a PR and comments Before/After bytes scanned, to catch
> cost regressions before merge. Dry-run only, WIF auth (no keys). Free in beta —
> feedback on usefulness + onboarding very welcome: <link>

### X / Twitter
> Caught a PR that would've 20x'd a BigQuery query's scan size — *after* it merged.
>
> So: a GitHub Action that dry-runs your changed dbt/BigQuery SQL on every PR and
> comments the Before→After cost. Dry-run only, no stored keys (WIF), ~$0.
>
> Free in beta 👉 <link> #dbt #BigQuery

### Qiita / Zenn (JP)
> **タイトル:** PRで BigQuery のスキャン量増加を検知する GitHub Action を作った
>
> パーティションフィルタが外れて、あるクエリの走査量が 4.2 GiB → 94.7 GiB に。
> 気づいたのは請求書でした。これを防ぐため、PR で変更された dbt/BigQuery SQL を
> dry run して Before/After のスキャン量をコメントする GitHub Action を作りました。
> dry run のみ（SQL は実行しない）、認証は WIF（鍵を保存しない）、fork PR は静的
> 解析のみ。自分の GitHub Actions 内で完結し、サーバー費はほぼ 0 円です。
> ベータ無料。導入の手間と警告の有用性についてフィードバックください: <link>
