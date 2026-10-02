"""Tests for static SQL analysis."""
from __future__ import annotations

from bq_cost_guard.analyzer import Finding, analyze_sql


def _messages(findings: list[Finding]) -> str:
    return " | ".join(f.message for f in findings)


def test_select_star_detected() -> None:
    findings = analyze_sql("SELECT * FROM `p.d.orders`", "orders.sql")
    assert any("SELECT *" in f.message for f in findings)
    assert all(f.filename == "orders.sql" for f in findings)


def test_cross_join_detected() -> None:
    sql = "SELECT a.id FROM `p.d.a` a CROSS JOIN `p.d.b` b"
    findings = analyze_sql(sql, "cross.sql")
    assert any("CROSS JOIN" in f.message for f in findings)


def test_clean_sql_has_no_findings() -> None:
    sql = "SELECT id, name FROM `p.d.orders` WHERE created_at >= '2024-01-01'"
    findings = analyze_sql(sql, "clean.sql")
    assert findings == []


def test_empty_sql_returns_empty() -> None:
    assert analyze_sql("", "empty.sql") == []
    assert analyze_sql("   \n  ", "whitespace.sql") == []


def test_select_star_and_cross_join_together() -> None:
    sql = "SELECT * FROM `p.d.a` CROSS JOIN `p.d.b`"
    findings = analyze_sql(sql, "both.sql")
    msgs = _messages(findings)
    assert "SELECT *" in msgs
    assert "CROSS JOIN" in msgs


def test_count_star_is_not_select_star() -> None:
    # COUNT(*) should not trigger a SELECT * finding when parsed by sqlglot.
    sql = "SELECT COUNT(*) AS n FROM `p.d.orders`"
    findings = analyze_sql(sql, "count.sql")
    assert not any("SELECT *" in f.message for f in findings)


def test_malformed_sql_does_not_raise() -> None:
    # Must never raise, even on garbage input.
    findings = analyze_sql("SELEKT ** FRON (((", "bad.sql")
    assert isinstance(findings, list)
