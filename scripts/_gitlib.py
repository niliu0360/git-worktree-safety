#!/usr/bin/env python3
"""Shared read-only Git inspection helpers for git-worktree-safety."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


class GitInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


def run_git(
    repo: Path,
    args: Iterable[str],
    *,
    check: bool = True,
    env: Optional[dict[str, str]] = None,
) -> GitResult:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    result = GitResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if check and result.returncode != 0:
        raise GitInspectionError(
            f"git command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}"
        )
    return result


def ensure_repo(repo: Path) -> Path:
    result = run_git(repo, ["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0 or not result.stdout:
        raise GitInspectionError(f"not a Git working tree: {repo}")
    return Path(result.stdout).resolve()


def git_dir(repo: Path) -> Path:
    value = run_git(repo, ["rev-parse", "--git-dir"]).stdout
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def common_git_dir(repo: Path) -> Path:
    value = run_git(repo, ["rev-parse", "--git-common-dir"]).stdout
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def current_branch(repo: Path) -> Optional[str]:
    value = run_git(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    return value.stdout or None


def head_oid(repo: Path) -> Optional[str]:
    value = run_git(repo, ["rev-parse", "--verify", "HEAD"], check=False)
    return value.stdout or None


def status_porcelain(repo: Path) -> list[str]:
    result = run_git(
        repo,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        check=False,
    )
    if result.returncode != 0:
        return [f"<status unavailable: {result.stderr or 'unknown error'}>"]
    return [line for line in result.stdout.splitlines() if line]


def operation_in_progress(repo: Path) -> list[str]:
    gd = git_dir(repo)
    common = common_git_dir(repo)
    checks = {
        "merge": gd / "MERGE_HEAD",
        "cherry-pick": gd / "CHERRY_PICK_HEAD",
        "revert": gd / "REVERT_HEAD",
        "bisect": gd / "BISECT_LOG",
        "rebase-merge": gd / "rebase-merge",
        "rebase-apply": gd / "rebase-apply",
        "sequencer": common / "sequencer",
    }
    return [name for name, path in checks.items() if path.exists()]


def parse_worktrees(repo: Path) -> list[dict[str, Any]]:
    result = run_git(repo, ["worktree", "list", "--porcelain", "-z"])
    tokens = result.stdout.split("\0") if result.stdout else []
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for token in tokens:
        if token == "":
            if current:
                records.append(current)
                current = {}
            continue
        if " " in token:
            key, value = token.split(" ", 1)
        else:
            key, value = token, True
        if key == "worktree" and current:
            records.append(current)
            current = {}
        current[key] = value
    if current:
        records.append(current)

    for record in records:
        branch = record.get("branch")
        if isinstance(branch, str) and branch.startswith("refs/heads/"):
            record["branch"] = branch[len("refs/heads/") :]
        if "worktree" in record:
            record["worktree"] = str(Path(str(record["worktree"])).resolve())
    return records


def default_branch(repo: Path) -> Optional[str]:
    symbolic = run_git(
        repo,
        ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        check=False,
    )
    if symbolic.returncode == 0 and symbolic.stdout.startswith("origin/"):
        return symbolic.stdout.split("/", 1)[1]
    for candidate in ("main", "master", "trunk"):
        if ref_exists(repo, f"refs/heads/{candidate}"):
            return candidate
    return None


def ref_exists(repo: Path, ref: str) -> bool:
    return run_git(repo, ["show-ref", "--verify", "--quiet", ref], check=False).returncode == 0


def resolve_commit(repo: Path, ref: str) -> Optional[str]:
    result = run_git(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False)
    return result.stdout or None


def upstream_for(repo: Path, branch: str) -> Optional[str]:
    result = run_git(
        repo,
        ["for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}"],
        check=False,
    )
    return result.stdout or None


def ahead_behind(repo: Path, left: str, right: str) -> Optional[tuple[int, int]]:
    result = run_git(
        repo,
        ["rev-list", "--left-right", "--count", f"{left}...{right}"],
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    parts = result.stdout.split()
    if len(parts) != 2:
        return None
    return int(parts[0]), int(parts[1])


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> Optional[bool]:
    result = run_git(repo, ["merge-base", "--is-ancestor", ancestor, descendant], check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def merge_tree_check(repo: Path, target: str, source: str) -> dict[str, Any]:
    """Run merge-tree with a temporary object store, leaving the source repo untouched."""
    source_objects = common_git_dir(repo) / "objects"
    with tempfile.TemporaryDirectory(prefix="gws-merge-tree-") as tmp:
        temp_objects = Path(tmp) / "objects"
        temp_objects.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["GIT_OBJECT_DIRECTORY"] = str(temp_objects)
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(source_objects)
        result = run_git(
            repo,
            ["merge-tree", "--write-tree", "--messages", target, source],
            check=False,
            env=env,
        )
    if result.returncode in (0, 1):
        lines = [line for line in (result.stdout + "\n" + result.stderr).splitlines() if line]
        return {
            "available": True,
            "clean": result.returncode == 0,
            "messages": lines[-20:],
            "repository_objects_modified": False,
        }
    return {
        "available": False,
        "clean": None,
        "messages": [result.stderr or "git merge-tree --write-tree is unavailable"],
        "repository_objects_modified": False,
    }


def branch_worktree(repo: Path, branch: str) -> Optional[dict[str, Any]]:
    for item in parse_worktrees(repo):
        if item.get("branch") == branch:
            return item
    return None


def directory_age_days(path: Path) -> Optional[float]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return max(0.0, (float(__import__("time").time()) - stat.st_mtime) / 86400.0)


def write_json(data: Any, destination: Optional[str]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    if destination:
        Path(destination).write_text(text + "\n", encoding="utf-8")
    print(text)


def severity(verdict: str) -> int:
    if verdict in {"SAFE_TO_WORK", "SAFE_TO_MERGE", "SAFE_TO_PUSH", "SAFE_CANDIDATE"}:
        return 0
    if verdict in {"WORK_WITH_WARNINGS", "MERGE_WITH_WARNINGS", "PUSH_WITH_WARNINGS", "REVIEW_REQUIRED"}:
        return 1
    return 2


def exit_for_verdict(verdict: str) -> int:
    return severity(verdict)
