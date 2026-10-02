"""Smoke tests tying the demo-dbt examples to analyzer behavior."""
from __future__ import annotations

from pathlib import Path

from bq_cost_guard.analyzer import analyze_sql

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-dbt"


def _read(rel: str) -> str:
    return (DEMO / rel).read_text(encoding="utf-8")


def test_demo_files_exist() -> None:
    assert (DEMO / "dbt_project.yml").exists()
    assert (DEMO / "models" / "daily_pageviews.sql").exists()
    assert (DEMO / "models" / "enwiki_hourly.sql").exists()
    assert (DEMO / "regression_example.sql").exists()


def test_good_model_has_no_select_star() -> None:
    findings = analyze_sql(_read("models/daily_pageviews.sql"), "daily_pageviews.sql")
    assert not any("SELECT *" in f.message for f in findings)


def test_regression_example_flags_select_star() -> None:
    findings = analyze_sql(_read("regression_example.sql"), "daily_pageviews.sql")
    assert any("SELECT *" in f.message for f in findings)
