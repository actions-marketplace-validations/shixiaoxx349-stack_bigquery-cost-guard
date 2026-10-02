"""Load and validate .bq-cost-guard.yml configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# Default thresholds
_DEFAULT_WARN_BYTES = 50 * 1024 ** 3       # 50 GiB
_DEFAULT_FAIL_BYTES = 500 * 1024 ** 3      # 500 GiB
_DEFAULT_WARN_INCREASE_PCT = 50
_DEFAULT_FAIL_INCREASE_PCT = 200


@dataclass
class DbtConfig:
    project_dir: str = "."
    profiles_dir: str = "."


@dataclass
class BigQueryConfig:
    project_id: str = ""
    location: str = "US"


@dataclass
class ThresholdConfig:
    warn_bytes: int = _DEFAULT_WARN_BYTES
    fail_bytes: int = _DEFAULT_FAIL_BYTES
    warn_increase_percent: int = _DEFAULT_WARN_INCREASE_PCT
    fail_increase_percent: int = _DEFAULT_FAIL_INCREASE_PCT


@dataclass
class AnalysisConfig:
    detect_select_star: bool = True
    detect_missing_partition_filter: bool = True


@dataclass
class PricingConfig:
    price_per_tib_usd: Optional[float] = None


@dataclass
class Config:
    version: int = 1
    dbt: DbtConfig = field(default_factory=DbtConfig)
    bigquery: BigQueryConfig = field(default_factory=BigQueryConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    fail_on_threshold: bool = False


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file, applying defaults for missing fields."""
    if config_path is None:
        config_path = os.environ.get("BQ_COST_GUARD_CONFIG", ".bq-cost-guard.yml")

    path = Path(config_path)
    if not path.exists():
        return Config()

    with path.open() as f:
        raw: dict = yaml.safe_load(f) or {}

    cfg = Config()
    cfg.version = int(raw.get("version", 1))
    cfg.fail_on_threshold = bool(raw.get("fail_on_threshold", False))

    if dbt_raw := raw.get("dbt"):
        cfg.dbt = DbtConfig(
            project_dir=str(dbt_raw.get("project_dir", ".")),
            profiles_dir=str(dbt_raw.get("profiles_dir", ".")),
        )

    if bq_raw := raw.get("bigquery"):
        cfg.bigquery = BigQueryConfig(
            project_id=str(bq_raw.get("project_id", "")),
            location=str(bq_raw.get("location", "US")),
        )

    if th_raw := raw.get("thresholds"):
        cfg.thresholds = ThresholdConfig(
            warn_bytes=int(th_raw.get("warn_bytes", _DEFAULT_WARN_BYTES)),
            fail_bytes=int(th_raw.get("fail_bytes", _DEFAULT_FAIL_BYTES)),
            warn_increase_percent=int(
                th_raw.get("warn_increase_percent", _DEFAULT_WARN_INCREASE_PCT)
            ),
            fail_increase_percent=int(
                th_raw.get("fail_increase_percent", _DEFAULT_FAIL_INCREASE_PCT)
            ),
        )

    if an_raw := raw.get("analysis"):
        cfg.analysis = AnalysisConfig(
            detect_select_star=bool(an_raw.get("detect_select_star", True)),
            detect_missing_partition_filter=bool(
                an_raw.get("detect_missing_partition_filter", True)
            ),
        )

    if pr_raw := raw.get("pricing"):
        price = pr_raw.get("price_per_tib_usd")
        cfg.pricing = PricingConfig(
            price_per_tib_usd=float(price) if price is not None else None
        )

    return cfg
