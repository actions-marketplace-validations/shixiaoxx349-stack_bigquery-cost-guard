"""GitHub API helpers: changed files, PR comments, fork detection."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

from .report import COMMENT_MARKER


def _api_url() -> str:
    return os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def _token() -> str:
    return os.environ.get("GITHUB_TOKEN", "")


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "")


def _make_request(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
) -> dict | list:
    token = _token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API {method} {url} returned {exc.code}: {body[:200]}"
        ) from exc


def is_fork_pr() -> bool:
    """Return True if the current PR originates from a fork repository.

    Reads GITHUB_EVENT_PATH to inspect the event payload.  Falls back to
    False (i.e. safe to run) only if the event file cannot be read.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return False
    try:
        with open(event_path) as f:
            event: dict = json.load(f)
        pr = event.get("pull_request", {})
        head_repo = pr.get("head", {}).get("repo", {})
        fork: bool = head_repo.get("fork", False)
        return fork
    except Exception as exc:
        print(
            f"[bq-cost-guard] Could not determine fork status: {exc}",
            file=sys.stderr,
        )
        return False


def get_changed_sql_files(base_sha: str, head_sha: str) -> list[str]:
    """Return a list of .sql file paths changed between *base_sha* and *head_sha*."""
    repo = _repo()
    if not repo:
        print("[bq-cost-guard] GITHUB_REPOSITORY not set", file=sys.stderr)
        return []

    url = f"{_api_url()}/repos/{repo}/compare/{base_sha}...{head_sha}"
    try:
        data = _make_request(url)
    except RuntimeError as exc:
        print(f"[bq-cost-guard] get_changed_sql_files failed: {exc}", file=sys.stderr)
        return []

    files = data.get("files", []) if isinstance(data, dict) else []
    return [
        f["filename"]
        for f in files
        if isinstance(f, dict)
        and f.get("filename", "").endswith(".sql")
        and f.get("status") != "removed"
    ]


def post_or_update_comment(pr_number: int, body: str) -> None:
    """Post a PR comment containing *body*, or update the existing one.

    Identifies existing comments by the ``COMMENT_MARKER`` HTML comment.
    Never logs *body* content (may contain SQL fragments from model names).
    """
    repo = _repo()
    if not repo:
        print("[bq-cost-guard] GITHUB_REPOSITORY not set — skipping comment", file=sys.stderr)
        return

    # List existing comments
    comments_url = f"{_api_url()}/repos/{repo}/issues/{pr_number}/comments"
    try:
        comments = _make_request(comments_url)
    except RuntimeError as exc:
        print(f"[bq-cost-guard] Could not list PR comments: {exc}", file=sys.stderr)
        return

    existing_id: Optional[int] = None
    if isinstance(comments, list):
        for comment in comments:
            if COMMENT_MARKER in comment.get("body", ""):
                existing_id = comment["id"]
                break

    payload = json.dumps({"body": body}).encode()
    try:
        if existing_id:
            url = f"{_api_url()}/repos/{repo}/issues/comments/{existing_id}"
            _make_request(url, method="PATCH", data=payload)
            print("[bq-cost-guard] Updated existing PR comment.", file=sys.stderr)
        else:
            _make_request(comments_url, method="POST", data=payload)
            print("[bq-cost-guard] Posted new PR comment.", file=sys.stderr)
    except RuntimeError as exc:
        print(f"[bq-cost-guard] Could not post/update comment: {exc}", file=sys.stderr)
