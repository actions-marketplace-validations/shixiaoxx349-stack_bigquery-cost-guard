"""Tests for config loading and defaults."""
from __future__ import annotations

from pathlib import Path

from bq_cost_guard.config import (
    _DEFAULT_FAIL_BYTES,
    _DEFAULT_WARN_BYTES,
    Config,
    load_config,
)


def test_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "does-not-exist.yml")
    assert isinstance(cfg, Config)
    assert cfg.version == 1
    assert cfg.thresholds.warn_bytes == _DEFAULT_WARN_BYTES
    assert cfg.thresholds.fail_bytes == _DEFAULT_FAIL_BYTES
    assert cfg.thresholds.warn_increase_percent == 50
    assert cfg.thresholds.fail_increase_percent == 200
    assert cfg.bigquery.location == "US"
    assert cfg.fail_on_threshold is False
    assert cfg.pricing.price_per_tib_usd is None


def test_load_full_config(tmp_path: Path) -> None:
    content = """
version: 1
fail_on_threshold: true
dbt:
  project_dir: ./analytics
  profiles_dir: ./analytics
bigquery:
  project_id: my-project
  location: asia-northeast1
thresholds:
  warn_bytes: 1073741824
  fail_bytes: 10737418240
  warn_increase_percent: 25
  fail_increase_percent: 100
analysis:
  detect_select_star: false
  detect_missing_partition_filter: true
pricing:
  price_per_tib_usd: 6.25
"""
    path = tmp_path / ".bq-cost-guard.yml"
    path.write_text(content, encoding="utf-8")

    cfg = load_config(path)
    assert cfg.fail_on_threshold is True
    assert cfg.dbt.project_dir == "./analytics"
    assert cfg.bigquery.project_id == "my-project"
    assert cfg.bigquery.location == "asia-northeast1"
    assert cfg.thresholds.warn_bytes == 1073741824
    assert cfg.thresholds.fail_bytes == 10737418240
    assert cfg.thresholds.warn_increase_percent == 25
    assert cfg.thresholds.fail_increase_percent == 100
    assert cfg.analysis.detect_select_star is False
    assert cfg.pricing.price_per_tib_usd == 6.25


def test_partial_config_falls_back_to_defaults(tmp_path: Path) -> None:
    content = """
bigquery:
  project_id: only-project
"""
    path = tmp_path / ".bq-cost-guard.yml"
    path.write_text(content, encoding="utf-8")

    cfg = load_config(path)
    assert cfg.bigquery.project_id == "only-project"
    # Unspecified sections keep defaults
    assert cfg.thresholds.warn_bytes == _DEFAULT_WARN_BYTES
    assert cfg.bigquery.location == "US"


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    path = tmp_path / ".bq-cost-guard.yml"
    path.write_text("", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.thresholds.fail_bytes == _DEFAULT_FAIL_BYTES
