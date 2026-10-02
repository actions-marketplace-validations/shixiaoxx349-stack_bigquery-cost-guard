"""Guards for scripts/setup-gcp.sh — the generated workflow must reference the
published Action's owner, not the customer's repo owner."""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup-gcp.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_action_ref_points_to_publisher() -> None:
    text = _text()
    # Default must target the published Action repo, not be derived from the user's repo.
    assert "shixiaoxx349-stack/bigquery-cost-guard@" in text


def test_generated_workflow_does_not_derive_action_from_customer_repo() -> None:
    # Regression: an earlier version printed ${GITHUB_REPO%/*}/bigquery-cost-guard,
    # which resolves to the CUSTOMER's org and breaks for every external user.
    text = _text()
    assert "${GITHUB_REPO%/*}/bigquery-cost-guard" not in text


def test_generated_workflow_uses_action_ref_variable() -> None:
    text = _text()
    assert "uses: ${ACTION_REF}" in text


def test_data_viewer_not_granted_project_wide_by_default() -> None:
    # Project-wide dataViewer must be behind the explicit --all-datasets opt-in.
    text = _text()
    assert "--all-datasets" in text
    assert '"${ALL_DATASETS}" -eq 1' in text
