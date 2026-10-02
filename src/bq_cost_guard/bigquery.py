"""BigQuery Dry Run wrapper — NEVER executes queries."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class DryRunResult:
    bytes_processed: Optional[int]
    error: Optional[str]
    is_valid: bool


def dry_run_query(sql: str, project_id: str, location: str = "US") -> DryRunResult:
    """Estimate bytes scanned for *sql* using BigQuery dry run.

    Always uses ``dry_run=True``.  Never executes the query.
    Catches all exceptions and returns them as an error DryRunResult.
    """
    try:
        from google.cloud import bigquery  # type: ignore[import-untyped]
    except ImportError:
        return DryRunResult(
            bytes_processed=None,
            error="google-cloud-bigquery is not installed",
            is_valid=False,
        )

    try:
        client = bigquery.Client(project=project_id, location=location)
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(sql, job_config=job_config, location=location)
        return DryRunResult(
            bytes_processed=job.total_bytes_processed,
            error=None,
            is_valid=True,
        )
    except Exception as exc:
        # Log to stderr only — never log the SQL content or any tokens
        print(
            f"[bq-cost-guard] dry run error for project={project_id!r}: {type(exc).__name__}",
            file=sys.stderr,
        )
        return DryRunResult(
            bytes_processed=None,
            error=str(exc),
            is_valid=False,
        )
