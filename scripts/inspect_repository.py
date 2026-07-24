#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _control_adapter import add_format_argument, format_report
from _gitlib import (
    GitInspectionError,
    ahead_behind,
    current_branch,
    default_branch,
    ensure_repo,
    head_oid,
    operation_in_progress,
    parse_worktrees,
    status_porcelain,
    upstream_for,
    write_json,
)


def build_report(repo_arg: str) -> dict:
    repo = ensure_repo(Path(repo_arg).resolve())
    branch = current_branch(repo)
    upstream = upstream_for(repo, branch) if branch else None
    divergence = ahead_behind(repo, branch, upstream) if branch and upstream else None
    dirty = status_porcelain(repo)
    operations = operation_in_progress(repo)
    warnings: list[str] = []
    if branch is None:
        warnings.append("HEAD is detached")
    if dirty:
        warnings.append(f"working tree has {len(dirty)} changed path(s)")
    if operations:
        warnings.append("Git operation in progress: " + ", ".join(operations))
    if branch and not upstream:
        warnings.append("current branch has no configured upstream")

    return {
        "schema_version": "0.1.0",
        "tool": "inspect_repository",
        "repository_root": str(repo),
        "head": head_oid(repo),
        "current_branch": branch,
        "detached_head": branch is None,
        "default_branch": default_branch(repo),
        "upstream": upstream,
        "ahead": divergence[0] if divergence else None,
        "behind": divergence[1] if divergence else None,
        "dirty": bool(dirty),
        "status_entries": dirty,
        "operations_in_progress": operations,
        "worktrees": parse_worktrees(repo),
        "warnings": warnings,
        "limitations": [
            "No network request or git fetch was performed.",
            "This report cannot prove that no other process or AI session is using a worktree.",
        ],
        "verdict": "INSPECTED_WITH_WARNINGS" if warnings else "INSPECTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Git repository inspection.")
    parser.add_argument("--repo", default=".", help="Path inside the target Git worktree")
    parser.add_argument("--output", help="Also write the JSON report to this path")
    add_format_argument(parser)
    args = parser.parse_args()
    try:
        report = build_report(args.repo)
    except GitInspectionError as exc:
        report = {
            "schema_version": "0.1.0",
            "tool": "inspect_repository",
            "verdict": "INVALID",
            "repository_root": str(Path(args.repo).resolve()),
            "errors": [str(exc)],
        }
        write_json(format_report(report, args.format), args.output)
        return 2
    write_json(format_report(report, args.format), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
