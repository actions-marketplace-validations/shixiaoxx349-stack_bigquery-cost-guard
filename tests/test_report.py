"""Tests for report formatting and comment rendering."""
from __future__ import annotations

from bq_cost_guard.analyzer import Finding
from bq_cost_guard.report import (
    COMMENT_MARKER,
    ModelResult,
    classify_status,
    estimate_cost_usd,
    format_bytes,
    format_comment,
    format_percent_change,
    format_usd,
)

GIB = 1024**3
TIB = 1024**4


def _classify(before, after, findings=False, has_error=False):
    return classify_status(
        before_bytes=before,
        after_bytes=after,
        has_findings=findings,
        warn_bytes=50 * GIB,
        fail_bytes=500 * GIB,
        warn_increase_percent=50,
        fail_increase_percent=200,
        has_error=has_error,
    )


def test_format_bytes() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.0 KiB"
    assert format_bytes(1024**2) == "1.0 MiB"
    assert format_bytes(1024**3) == "1.0 GiB"
    assert format_bytes(1024**4) == "1.0 TiB"
    assert format_bytes(None) == "N/A"
    assert format_bytes(-5) == "N/A"


def test_format_bytes_fractional() -> None:
    assert format_bytes(int(4.2 * 1024**3)) == "4.2 GiB"


def test_format_percent_change() -> None:
    assert format_percent_change(100, 200) == "+100%"
    assert format_percent_change(100, 50) == "-50%"
    assert format_percent_change(100, 100) == "+0%"
    assert format_percent_change(None, 100) == "N/A"
    assert format_percent_change(100, None) == "N/A"


def test_format_percent_change_from_zero() -> None:
    assert format_percent_change(0, 100) == "+∞"
    assert format_percent_change(0, 0) == "0%"


def test_comment_has_marker() -> None:
    body = format_comment([])
    assert body.startswith(COMMENT_MARKER)
    assert "does not execute the analyzed SQL" in body


def test_comment_renders_table_rows() -> None:
    results = [
        ModelResult(
            model_name="orders_daily",
            filename="models/orders_daily.sql",
            before_bytes=None,
            after_bytes=int(94.7 * 1024**3),
            findings=[
                Finding(
                    severity="warning",
                    message="SELECT * detected",
                    filename="models/orders_daily.sql",
                )
            ],
            status="warn",
        ),
    ]
    body = format_comment(results)
    assert COMMENT_MARKER in body
    assert "BigQuery Cost Guard" in body
    assert "`orders_daily`" in body
    assert "94.7 GiB" in body
    assert "⚠️" in body
    assert "### Findings" in body
    assert "SELECT * detected" in body


def test_comment_renders_error_section() -> None:
    results = [
        ModelResult(
            model_name="broken",
            filename="models/broken.sql",
            before_bytes=None,
            after_bytes=None,
            findings=[],
            status="error",
            error="Syntax error near FROM",
        ),
    ]
    body = format_comment(results)
    assert "### Errors" in body
    assert "Syntax error near FROM" in body


def test_empty_results_message() -> None:
    body = format_comment([])
    assert "No changed SQL files detected" in body


# --- Phase 1B: status classification ---------------------------------------

def test_classify_ok_when_small_and_clean() -> None:
    assert _classify(before=1 * GIB, after=1 * GIB) == "ok"


def test_classify_error_wins() -> None:
    assert _classify(before=None, after=None, has_error=True) == "error"


def test_classify_warn_on_absolute_bytes() -> None:
    assert _classify(before=None, after=60 * GIB) == "warn"


def test_classify_fail_on_absolute_bytes() -> None:
    assert _classify(before=None, after=600 * GIB) == "fail"


def test_classify_warn_on_increase_percent() -> None:
    # +100% increase (>= warn 50%, < fail 200%), both below absolute warn bytes
    assert _classify(before=1 * GIB, after=2 * GIB) == "warn"


def test_classify_fail_on_increase_percent() -> None:
    # +300% increase (>= fail 200%), below absolute warn bytes
    assert _classify(before=1 * GIB, after=4 * GIB) == "fail"


def test_classify_most_severe_wins() -> None:
    # small % increase but huge absolute -> fail
    assert _classify(before=400 * GIB, after=600 * GIB) == "fail"


def test_classify_findings_only_warn() -> None:
    assert _classify(before=None, after=None, findings=True) == "warn"


# --- Phase 1B: cost estimation ---------------------------------------------

def test_estimate_cost_usd() -> None:
    assert estimate_cost_usd(TIB, 6.25) == 6.25
    assert estimate_cost_usd(TIB // 2, 6.25) == 3.125
    assert estimate_cost_usd(None, 6.25) is None
    assert estimate_cost_usd(TIB, None) is None


def test_format_usd() -> None:
    assert format_usd(6.25) == "$6.25"
    assert format_usd(None) == "N/A"
    assert format_usd(1234.5) == "$1,234.50"


def test_comment_cost_line_before_after() -> None:
    results = [
        ModelResult(
            model_name="orders",
            filename="models/orders.sql",
            before_bytes=1 * TIB,
            after_bytes=2 * TIB,
            findings=[],
            status="warn",
        )
    ]
    body = format_comment(results, price_per_tib_usd=6.25)
    assert "Estimated on-demand cost" in body
    assert "$6.25" in body   # before
    assert "$12.50" in body  # after
    assert "+$6.25" in body  # delta


def test_comment_no_cost_line_without_price() -> None:
    results = [
        ModelResult(
            model_name="orders",
            filename="models/orders.sql",
            before_bytes=1 * TIB,
            after_bytes=2 * TIB,
            findings=[],
            status="warn",
        )
    ]
    body = format_comment(results)
    assert "Estimated on-demand cost" not in body


def test_comment_renders_percent_change_when_before_known() -> None:
    results = [
        ModelResult(
            model_name="orders",
            filename="models/orders.sql",
            before_bytes=1 * GIB,
            after_bytes=3 * GIB,
            findings=[],
            status="fail",
        )
    ]
    body = format_comment(results)
    assert "+200%" in body
