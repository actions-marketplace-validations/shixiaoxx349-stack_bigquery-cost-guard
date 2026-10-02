"""dbt compile runner — subprocess wrapper."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def compile_project(
    project_dir: str = ".",
    profiles_dir: str = ".",
    timeout: int = 300,
) -> dict[str, str]:
    """Run ``dbt compile`` and return {model_name: compiled_sql_path}.

    Returns an empty dict if dbt is not installed or compilation fails.
    Never raises.
    """
    try:
        result = subprocess.run(
            ["dbt", "compile", "--project-dir", project_dir, "--profiles-dir", profiles_dir],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        print("[bq-cost-guard] dbt not found — skipping dbt compile", file=sys.stderr)
        return {}
    except subprocess.TimeoutExpired:
        print("[bq-cost-guard] dbt compile timed out", file=sys.stderr)
        return {}
    except Exception as exc:
        print(f"[bq-cost-guard] dbt compile error: {exc}", file=sys.stderr)
        return {}

    if result.returncode != 0:
        print(
            f"[bq-cost-guard] dbt compile failed (exit {result.returncode})",
            file=sys.stderr,
        )
        return {}

    # Walk the compiled target directory to collect model paths
    target_dir = Path(project_dir) / "target" / "compiled"
    if not target_dir.exists():
        return {}

    models: dict[str, str] = {}
    for sql_file in target_dir.rglob("*.sql"):
        model_name = sql_file.stem
        models[model_name] = str(sql_file)

    return models


def compile_at_ref(
    ref: str,
    project_dir: str = ".",
    profiles_dir: str = ".",
    timeout: int = 300,
) -> dict[str, str]:
    """Compile the dbt project as it existed at git *ref* in a throwaway worktree.

    Returns ``{model_name: compiled_sql_text}`` (content, not paths, because the
    worktree is deleted before returning). Empty dict on any failure. Never raises.
    Used for Phase 1B Before/After comparison.
    """
    if not ref:
        return {}

    worktree = tempfile.mkdtemp(prefix="bqcg-base-")
    # Resolve profiles_dir to an absolute path from the current (head) checkout so
    # the base compile reuses the same connection config even if the old revision
    # lacked it.
    abs_profiles = str(Path(profiles_dir).resolve())
    try:
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", worktree, ref],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if add.returncode != 0:
            print(
                f"[bq-cost-guard] git worktree add failed for base ref (exit {add.returncode})",
                file=sys.stderr,
            )
            return {}

        wt_project = str(Path(worktree) / project_dir)
        paths = compile_project(
            project_dir=wt_project,
            profiles_dir=abs_profiles,
            timeout=timeout,
        )
        # Read SQL content now, before the worktree is removed.
        return {name: get_compiled_sql(path) for name, path in paths.items()}
    except subprocess.TimeoutExpired:
        print("[bq-cost-guard] base worktree setup timed out", file=sys.stderr)
        return {}
    except Exception as exc:
        print(f"[bq-cost-guard] compile_at_ref error: {exc}", file=sys.stderr)
        return {}
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree],
            capture_output=True,
            text=True,
        )
        shutil.rmtree(worktree, ignore_errors=True)


def file_at_ref(ref: str, path: str) -> str:
    """Return the contents of *path* as of git *ref* via ``git show``.

    Empty string if the file did not exist at that ref or git fails. Never raises.
    Used for Before/After on plain (non-dbt) SQL repositories.
    """
    if not ref or not path:
        return ""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        print(f"[bq-cost-guard] git show failed for {path}: {exc}", file=sys.stderr)
        return ""
    if result.returncode != 0:
        return ""  # file likely new in this PR
    return result.stdout


def get_compiled_sql(compiled_path: str) -> str:
    """Read and return the compiled SQL from *compiled_path*.

    Returns empty string if the file cannot be read.
    """
    try:
        return Path(compiled_path).read_text(encoding="utf-8")
    except Exception as exc:
        print(
            f"[bq-cost-guard] Could not read compiled SQL at {compiled_path}: {exc}",
            file=sys.stderr,
        )
        return ""


def manifest_model_map(project_dir: str = ".") -> dict[str, str]:
    """Parse ``target/manifest.json`` and return {node_name: compiled_path}.

    Returns empty dict if manifest is missing or unparseable.
    """
    manifest_path = Path(project_dir) / "target" / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[bq-cost-guard] Could not parse manifest: {exc}", file=sys.stderr)
        return {}

    result: dict[str, str] = {}
    for node_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model":
            continue
        compiled_path = node.get("compiled_path") or node.get("compiled_sql")
        if compiled_path:
            result[node.get("name", node_id)] = str(
                Path(project_dir) / compiled_path
            )
    return result
