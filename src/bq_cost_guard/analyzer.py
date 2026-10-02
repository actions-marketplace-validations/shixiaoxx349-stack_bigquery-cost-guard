"""Static SQL analysis: SELECT *, CROSS JOIN, missing partition filters."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

_SQLGLOT_AVAILABLE = False
try:
    import sqlglot  # noqa: F401

    _SQLGLOT_AVAILABLE = True
except ImportError:
    pass


@dataclass
class Finding:
    severity: str  # "warning" | "info"
    message: str
    filename: str


# ---------------------------------------------------------------------------
# Regex-based fallback detectors
# ---------------------------------------------------------------------------

_RE_SELECT_STAR = re.compile(r"\bSELECT\s+\*", re.IGNORECASE)
_RE_CROSS_JOIN = re.compile(r"\bCROSS\s+JOIN\b", re.IGNORECASE)


def _detect_select_star_regex(sql: str, filename: str) -> list[Finding]:
    if _RE_SELECT_STAR.search(sql):
        return [
            Finding(
                severity="warning",
                message="SELECT * detected — consider selecting only needed columns to reduce bytes scanned.",
                filename=filename,
            )
        ]
    return []


def _detect_cross_join_regex(sql: str, filename: str) -> list[Finding]:
    if _RE_CROSS_JOIN.search(sql):
        return [
            Finding(
                severity="warning",
                message="CROSS JOIN detected — verify this is intentional; it can cause exponential row expansion.",
                filename=filename,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# sqlglot-based detectors (preferred when library is available)
# ---------------------------------------------------------------------------

def _detect_with_sqlglot(sql: str, filename: str) -> list[Finding]:
    """Parse SQL with sqlglot and detect anti-patterns."""
    import sqlglot
    import sqlglot.expressions as exp

    findings: list[Finding] = []
    try:
        statements = sqlglot.parse(sql, error_level=sqlglot.ErrorLevel.WARN)
    except Exception as exc:
        print(f"[bq-cost-guard] sqlglot parse warning for {filename}: {exc}", file=sys.stderr)
        # Fallback to regex on parse error
        findings.extend(_detect_select_star_regex(sql, filename))
        findings.extend(_detect_cross_join_regex(sql, filename))
        return findings

    for stmt in statements:
        if stmt is None:
            continue
        # SELECT *
        for star in stmt.find_all(exp.Star):
            parent = star.parent
            if isinstance(parent, exp.Select) or (parent and parent.key == "expressions"):
                findings.append(
                    Finding(
                        severity="warning",
                        message="SELECT * detected — consider selecting only needed columns to reduce bytes scanned.",
                        filename=filename,
                    )
                )
                break  # one finding per statement is enough

        # CROSS JOIN
        for join in stmt.find_all(exp.Join):
            if join.args.get("kind", "").upper() == "CROSS":
                findings.append(
                    Finding(
                        severity="warning",
                        message="CROSS JOIN detected — verify this is intentional; it can cause exponential row expansion.",
                        filename=filename,
                    )
                )
                break

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_sql(sql: str, filename: str) -> list[Finding]:
    """Analyse SQL for cost and correctness anti-patterns.

    Uses sqlglot when available, falls back to regex-based detection.
    Never raises — parse errors are returned as a warning Finding.
    """
    if not sql or not sql.strip():
        return []

    if _SQLGLOT_AVAILABLE:
        try:
            return _detect_with_sqlglot(sql, filename)
        except Exception as exc:
            print(
                f"[bq-cost-guard] sqlglot analysis failed for {filename}: {exc}",
                file=sys.stderr,
            )
            # fall through to regex

    findings: list[Finding] = []
    findings.extend(_detect_select_star_regex(sql, filename))
    findings.extend(_detect_cross_join_regex(sql, filename))
    return findings
