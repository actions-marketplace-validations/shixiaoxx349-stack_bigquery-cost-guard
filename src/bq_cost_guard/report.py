"""Format PR comment markdown from analysis results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .analyzer import Finding

# HTML marker used to identify and update existing comments
COMMENT_MARKER = "<!-- bq-cost-guard -->"


@dataclass
class ModelResult:
    model_name: str
    filename: str
    before_bytes: Optional[int]
    after_bytes: Optional[int]
    findings: list[Finding] = field(default_factory=list)
    status: str = "ok"  # "ok" | "warn" | "fail" | "error"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_bytes(n: Optional[int]) -> str:
    """Return a human-readable byte string, e.g. '1.5 GiB'."""
    if n is None:
        return "N/A"
    if n < 0:
        return "N/A"
    for unit, threshold in [
        ("TiB", 1024 ** 4),
        ("GiB", 1024 ** 3),
        ("MiB", 1024 ** 2),
        ("KiB", 1024),
    ]:
        if n >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def estimate_cost_usd(n_bytes: Optional[int], price_per_tib_usd: Optional[float]) -> Optional[float]:
    """Estimate on-demand query cost in USD for *n_bytes*, or None if not computable."""
    if n_bytes is None or price_per_tib_usd is None:
        return None
    return n_bytes / (1024 ** 4) * price_per_tib_usd


def format_usd(amount: Optional[float]) -> str:
    """Format a USD amount, e.g. '$0.59' or 'N/A'."""
    if amount is None:
        return "N/A"
    return f"${amount:,.2f}"


def format_percent_change(before: Optional[int], after: Optional[int]) -> str:
    """Return a percent-change string like '+2155%' or 'N/A'."""
    if before is None or after is None:
        return "N/A"
    if before == 0:
        return "+∞" if after > 0 else "0%"
    pct = (after - before) / before * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}%"


def _status_icon(status: str) -> str:
    return {
        "ok": "✅",
        "warn": "⚠️",
        "fail": "❌",
        "error": "🔴",
    }.get(status, "❓")


def classify_status(
    before_bytes: Optional[int],
    after_bytes: Optional[int],
    has_findings: bool,
    warn_bytes: int,
    fail_bytes: int,
    warn_increase_percent: int,
    fail_increase_percent: int,
    has_error: bool = False,
) -> str:
    """Return the overall status for a model from absolute and relative signals.

    Precedence: error > fail > warn > ok. Both absolute byte thresholds and the
    Before/After increase thresholds are considered; the most severe wins.
    """
    if has_error:
        return "error"

    rank = 0  # 0=ok, 1=warn, 2=fail

    if after_bytes is not None:
        if after_bytes >= fail_bytes:
            rank = max(rank, 2)
        elif after_bytes >= warn_bytes:
            rank = max(rank, 1)

        if before_bytes is not None and before_bytes > 0:
            pct = (after_bytes - before_bytes) / before_bytes * 100
            if pct >= fail_increase_percent:
                rank = max(rank, 2)
            elif pct >= warn_increase_percent:
                rank = max(rank, 1)

    if has_findings:
        rank = max(rank, 1)

    return {0: "ok", 1: "warn", 2: "fail"}[rank]


# ---------------------------------------------------------------------------
# Comment builder
# ---------------------------------------------------------------------------

def format_comment(
    results: list[ModelResult],
    price_per_tib_usd: Optional[float] = None,
) -> str:
    """Build a full PR comment body from a list of ModelResult objects.

    When *price_per_tib_usd* is set, an aggregate on-demand cost line is added.
    """
    lines: list[str] = [COMMENT_MARKER, "", "## 🛡 BigQuery Cost Guard", ""]

    if not results:
        lines += [
            "_No changed SQL files detected._",
            "",
            "---",
            "> Cost estimated via BigQuery dry run. Cost Guard does not execute the analyzed SQL.",
        ]
        return "\n".join(lines)

    # Summary table
    lines += [
        "| Model | Before | After | Change | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for r in results:
        change = format_percent_change(r.before_bytes, r.after_bytes)
        icon = _status_icon(r.status)
        lines.append(
            f"| `{r.model_name}` "
            f"| {format_bytes(r.before_bytes)} "
            f"| {format_bytes(r.after_bytes)} "
            f"| {change} "
            f"| {icon} |"
        )

    lines.append("")

    # Optional aggregate cost line (only when a price is configured)
    if price_per_tib_usd is not None:
        before_total = sum(r.before_bytes for r in results if r.before_bytes is not None)
        after_total = sum(r.after_bytes for r in results if r.after_bytes is not None)
        has_before = any(r.before_bytes is not None for r in results)
        has_after = any(r.after_bytes is not None for r in results)
        if has_after:
            after_cost = estimate_cost_usd(after_total, price_per_tib_usd)
            if has_before:
                before_cost = estimate_cost_usd(before_total, price_per_tib_usd)
                delta = (after_cost or 0) - (before_cost or 0)
                sign = "+" if delta >= 0 else "-"
                lines += [
                    f"**Estimated on-demand cost (per run):** "
                    f"{format_usd(before_cost)} → {format_usd(after_cost)} "
                    f"({sign}{format_usd(abs(delta))}) at ${price_per_tib_usd:g}/TiB",
                    "",
                ]
            else:
                lines += [
                    f"**Estimated on-demand cost (per run):** {format_usd(after_cost)} "
                    f"at ${price_per_tib_usd:g}/TiB",
                    "",
                ]

    # Findings section
    all_findings = [f for r in results for f in r.findings]
    if all_findings:
        lines += ["### Findings", ""]
        for finding in all_findings:
            bullet = "⚠️" if finding.severity == "warning" else "ℹ️"
            lines.append(f"- {bullet} **{finding.filename}**: {finding.message}")
        lines.append("")

    # Error section
    errors = [r for r in results if r.status == "error" and r.error]
    if errors:
        lines += ["### Errors", ""]
        for r in errors:
            lines.append(f"- `{r.model_name}`: {r.error}")
        lines.append("")

    lines += [
        "---",
        "> Cost estimated via BigQuery dry run. Cost Guard does not execute the analyzed SQL.",
    ]

    return "\n".join(lines)
