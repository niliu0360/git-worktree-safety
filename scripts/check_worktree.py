#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from _control_adapter import add_format_argument, format_report
from _gitlib import (
    GitInspectionError,
    current_branch,
    ensure_repo,
    exit_for_verdict,
    operation_in_progress,
    parse_worktrees,
    status_porcelain,
    upstream_for,
    write_json,
)


def build_report(
    repo_arg: str,
    expected_branch: Optional[str],
    require_clean: bool,
    require_upstream: bool,
) -> dict:
    repo = ensure_repo(Path(repo_arg).resolve())
    branch = current_branch(repo)
    dirty_entries = status_porcelain(repo)
    operations = operation_in_progress(repo)
    worktrees = parse_worktrees(repo)
    current_record = next(
        (item for item in worktrees if item.get("worktree") == str(repo)), None
    )
    upstream = upstream_for(repo, branch) if branch else None

    blockers: list[dict] = []
    warnings: list[dict] = []
    checks: list[dict] = []

    def check(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})
        item = {"check": name, "detail": detail}
        if status == "block":
            blockers.append(item)
        elif status == "warn":
            warnings.append(item)

    check(
        "detached_head",
        "block" if branch is None else "pass",
        "HEAD is detached" if branch is None else f"current branch is {branch}",
    )
    if expected_branch:
        check(
            "expected_branch",
            "pass" if branch == expected_branch else "block",
            f"expected {expected_branch}; found {branch or '<detached>'}",
        )
    check(
        "git_operation",
        "block" if operations else "pass",
        "in progress: " + ", ".join(operations) if operations else "none",
    )
    check(
        "working_tree_cleanliness",
        "block" if dirty_entries and require_clean else ("warn" if dirty_entries else "pass"),
        f"{len(dirty_entries)} changed path(s)" if dirty_entries else "clean",
    )
    check(
        "upstream",
        "block" if require_upstream and not upstream else ("warn" if not upstream else "pass"),
        upstream or "no configured upstream",
    )
    if current_record and current_record.get("locked") is not None:
        check("worktree_locked", "warn", "current worktree is marked locked")
    else:
        check("worktree_locked", "pass", "not marked locked")

    if blockers:
        verdict = "DO_NOT_MODIFY"
    elif warnings:
        verdict = "WORK_WITH_WARNINGS"
    else:
        verdict = "SAFE_TO_WORK"

    return {
        "schema_version": "0.1.0",
        "tool": "check_worktree",
        "mode": "start_work_check",
        "verdict": verdict,
        "repository_root": str(repo),
        "current_branch": branch,
        "expected_branch": expected_branch,
        "upstream": upstream,
        "dirty": bool(dirty_entries),
        "status_entries": dirty_entries,
        "operations_in_progress": operations,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "limitations": [
            "The check is read-only and does not claim or lock the worktree.",
            "Git metadata cannot prove that no other editor, process, or AI session is using this path.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the current worktree is safe to modify.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--expected-branch")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--require-upstream", action="store_true")
    parser.add_argument("--output")
    add_format_argument(parser)
    args = parser.parse_args()
    try:
        report = build_report(
            args.repo, args.expected_branch, args.require_clean, args.require_upstream
        )
    except GitInspectionError as exc:
        report = {
            "schema_version": "0.1.0",
            "tool": "check_worktree",
            "mode": "start_work_check",
            "verdict": "INVALID",
            "repository_root": str(Path(args.repo).resolve()),
            "errors": [str(exc)],
        }
        write_json(format_report(report, args.format), args.output)
        return 2
    exit_code = exit_for_verdict(report["verdict"])
    write_json(format_report(report, args.format), args.output)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
