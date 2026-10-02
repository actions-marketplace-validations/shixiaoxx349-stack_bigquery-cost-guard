"""Entry point: ``bq-cost-guard`` CLI."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .analyzer import analyze_sql
from .bigquery import dry_run_query
from .config import load_config
from .dbt import compile_at_ref, compile_project, file_at_ref, get_compiled_sql
from .github import get_changed_sql_files, is_fork_pr, post_or_update_comment
from .report import ModelResult, classify_status, format_comment


# ---------------------------------------------------------------------------
# Subcommand: analyze
# ---------------------------------------------------------------------------

def _cmd_analyze(args: argparse.Namespace) -> int:
    """Perform static analysis on a single SQL file and print findings."""
    cfg = load_config(args.config)
    sql_path = Path(args.sql_file)

    if not sql_path.exists():
        print(f"ERROR: file not found: {sql_path}", file=sys.stderr)
        return 1

    sql = sql_path.read_text(encoding="utf-8")
    findings = analyze_sql(sql, sql_path.name)

    if not findings:
        print("No issues found.")
        return 0

    for f in findings:
        print(f"[{f.severity.upper()}] {f.filename}: {f.message}")

    # Also run dry run if project_id provided
    project_id = args.project_id or cfg.bigquery.project_id
    if project_id:
        location = args.location or cfg.bigquery.location
        result = dry_run_query(sql, project_id, location)
        if result.is_valid and result.bytes_processed is not None:
            from .report import format_bytes
            print(f"Dry run: {format_bytes(result.bytes_processed)} would be scanned.")
        elif result.error:
            print(f"Dry run error: {result.error}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# Subcommand: run  (full GitHub Actions pipeline)
# ---------------------------------------------------------------------------

def _determine_model_name(filename: str, dbt_models: dict[str, str]) -> str:
    stem = Path(filename).stem
    return stem


def _cmd_run(args: argparse.Namespace) -> int:
    """Full GitHub Actions pipeline mode."""
    cfg = load_config(args.config)

    # 1. Fork check — skip BigQuery for fork PRs (security)
    fork = is_fork_pr()
    if fork:
        print(
            "[bq-cost-guard] Fork PR detected — BigQuery dry run skipped. "
            "Running static analysis only.",
            file=sys.stderr,
        )

    # 2. Resolve changed SQL files
    base_sha = os.environ.get("GITHUB_BASE_REF_SHA") or os.environ.get("GITHUB_SHA", "")
    head_sha = os.environ.get("GITHUB_SHA", "")
    pr_number_str = os.environ.get("GITHUB_PR_NUMBER") or ""

    # Try reading from event payload
    if not pr_number_str:
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if event_path:
            try:
                import json
                with open(event_path) as f:
                    event = json.load(f)
                pr_number_str = str(
                    event.get("pull_request", {}).get("number", "")
                )
                if not base_sha:
                    base_sha = (
                        event.get("pull_request", {})
                        .get("base", {})
                        .get("sha", "")
                    )
                if not head_sha:
                    head_sha = (
                        event.get("pull_request", {})
                        .get("head", {})
                        .get("sha", "")
                    )
            except Exception as exc:
                print(f"[bq-cost-guard] Could not read event file: {exc}", file=sys.stderr)

    changed_files = get_changed_sql_files(base_sha, head_sha) if base_sha and head_sha else []
    if not changed_files:
        print("[bq-cost-guard] No changed SQL files found.", file=sys.stderr)

    # 3. dbt compile — head, and (Phase 1B) base for Before/After comparison
    dbt_models: dict[str, str] = {}
    base_models_sql: dict[str, str] = {}
    project_dir = cfg.dbt.project_dir
    is_dbt = (Path(project_dir) / "dbt_project.yml").exists()
    if is_dbt:
        dbt_models = compile_project(
            project_dir=project_dir,
            profiles_dir=cfg.dbt.profiles_dir,
        )
        # Base compile only matters when we can actually dry-run (not a fork) and
        # we have a base ref to check out.
        if not fork and base_sha and dbt_models:
            base_models_sql = compile_at_ref(
                base_sha,
                project_dir=project_dir,
                profiles_dir=cfg.dbt.profiles_dir,
            )

    # 4. Build results for each changed file
    results: list[ModelResult] = []
    project_id = cfg.bigquery.project_id or os.environ.get("BIGQUERY_PROJECT_ID", "")
    location = cfg.bigquery.location

    for filename in changed_files:
        model_name = _determine_model_name(filename, dbt_models)

        # Resolve head SQL: prefer dbt compiled output, fallback to raw file
        sql = ""
        if model_name in dbt_models:
            sql = get_compiled_sql(dbt_models[model_name])
        if not sql:
            try:
                sql = Path(filename).read_text(encoding="utf-8")
            except Exception as exc:
                print(
                    f"[bq-cost-guard] Cannot read {filename}: {exc}",
                    file=sys.stderr,
                )

        # Resolve base SQL for Before/After: dbt compiled base, else raw file at base ref
        base_sql = ""
        if model_name in base_models_sql:
            base_sql = base_models_sql[model_name]
        elif not is_dbt and base_sha:
            base_sql = file_at_ref(base_sha, filename)

        findings = analyze_sql(sql, filename) if sql else []

        # Dry run head + base (only if not fork and project_id configured)
        after_bytes = None
        before_bytes = None
        error_msg = None
        if not fork and project_id and sql:
            dr = dry_run_query(sql, project_id, location)
            if dr.is_valid:
                after_bytes = dr.bytes_processed
            else:
                error_msg = dr.error
            if base_sql:
                dr_base = dry_run_query(base_sql, project_id, location)
                if dr_base.is_valid:
                    before_bytes = dr_base.bytes_processed

        status = classify_status(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            has_findings=bool(findings),
            warn_bytes=cfg.thresholds.warn_bytes,
            fail_bytes=cfg.thresholds.fail_bytes,
            warn_increase_percent=cfg.thresholds.warn_increase_percent,
            fail_increase_percent=cfg.thresholds.fail_increase_percent,
            has_error=bool(error_msg),
        )

        results.append(
            ModelResult(
                model_name=model_name,
                filename=filename,
                before_bytes=before_bytes,
                after_bytes=after_bytes,
                findings=findings,
                status=status,
                error=error_msg,
            )
        )

    # 5. Format comment
    comment_body = format_comment(results, price_per_tib_usd=cfg.pricing.price_per_tib_usd)

    # 6. Post/update PR comment
    if pr_number_str:
        try:
            pr_number = int(pr_number_str)
            post_or_update_comment(pr_number, comment_body)
        except ValueError:
            print(
                f"[bq-cost-guard] Invalid PR number: {pr_number_str!r}",
                file=sys.stderr,
            )
    else:
        # Not in a PR context — print comment to stdout for debugging
        print(comment_body)

    # 7. Exit code
    if cfg.fail_on_threshold:
        if any(r.status == "fail" for r in results):
            print(
                "[bq-cost-guard] One or more models exceeded fail thresholds.",
                file=sys.stderr,
            )
            return 1

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bq-cost-guard",
        description="Estimate BigQuery cost impact of SQL changes in pull requests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze subcommand
    p_analyze = sub.add_parser("analyze", help="Analyse a single SQL file.")
    p_analyze.add_argument("--config", default=".bq-cost-guard.yml", help="Config file path.")
    p_analyze.add_argument("--sql-file", required=True, help="Path to SQL file.")
    p_analyze.add_argument("--project-id", default="", help="GCP project ID for dry run.")
    p_analyze.add_argument("--location", default="US", help="BigQuery location.")

    # run subcommand
    p_run = sub.add_parser("run", help="Full GitHub Actions pipeline mode.")
    p_run.add_argument("--config", default=".bq-cost-guard.yml", help="Config file path.")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        sys.exit(_cmd_analyze(args))
    elif args.command == "run":
        sys.exit(_cmd_run(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
