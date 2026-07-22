#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _gitlib import (
    GitInspectionError,
    ahead_behind,
    branch_worktree,
    current_branch,
    ensure_repo,
    exit_for_verdict,
    operation_in_progress,
    resolve_commit,
    status_porcelain,
    upstream_for,
    write_json,
)


def build_report(
    repo_arg: str,
    branch_arg: str | None,
    remote_ref: str | None,
    require_clean: bool,
) -> dict:
    repo = ensure_repo(Path(repo_arg).resolve())
    branch = branch_arg or current_branch(repo)
    blockers: list[dict] = []
    warnings: list[dict] = []
    checks: list[dict] = []

    def check(name: str, status: str, detail: str, data: dict | None = None) -> None:
        row = {"check": name, "status": status, "detail": detail}
        if data:
            row["data"] = data
        checks.append(row)
        issue = {"check": name, "detail": detail}
        if data:
            issue["data"] = data
        if status == "block":
            blockers.append(issue)
        elif status == "warn":
            warnings.append(issue)

    if not branch:
        check("branch", "block", "HEAD is detached and no --branch was provided")
    else:
        oid = resolve_commit(repo, branch)
        check("branch", "pass" if oid else "block", oid or f"unknown ref: {branch}")

    upstream = remote_ref or (upstream_for(repo, branch) if branch else None)
    if not upstream:
        check("remote_ref", "block", "no upstream or --remote-ref is available")
    else:
        check("remote_ref", "pass", upstream)

    wt = branch_worktree(repo, branch) if branch else None
    if wt:
        path = Path(str(wt["worktree"]))
        operations = operation_in_progress(path)
        dirty = status_porcelain(path)
        check(
            "git_operation",
            "block" if operations else "pass",
            ", ".join(operations) if operations else "none",
            {"worktree": str(path)},
        )
        check(
            "worktree_clean",
            "block" if dirty and require_clean else ("warn" if dirty else "pass"),
            f"{len(dirty)} changed path(s)" if dirty else "clean",
            {"worktree": str(path), "status_entries": dirty},
        )

    if branch and upstream and resolve_commit(repo, branch) and resolve_commit(repo, upstream):
        divergence = ahead_behind(repo, branch, upstream)
        ahead, behind = divergence if divergence else (None, None)
        if behind:
            status = "block"
        elif ahead == 0:
            status = "warn"
        else:
            status = "pass"
        check(
            "remote_divergence",
            status,
            f"ahead={ahead}; behind={behind}",
            {"branch": branch, "remote_ref": upstream},
        )
    elif upstream:
        check(
            "remote_divergence",
            "block",
            f"remote-tracking ref is unavailable locally: {upstream}",
        )

    if blockers:
        verdict = "DO_NOT_PUSH"
    elif warnings:
        verdict = "PUSH_WITH_WARNINGS"
    else:
        verdict = "SAFE_TO_PUSH"

    return {
        "schema_version": "0.1.0",
        "tool": "check_push_readiness",
        "mode": "merge_push_check",
        "operation": "push",
        "verdict": verdict,
        "repository_root": str(repo),
        "branch": branch,
        "remote_ref": upstream,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "limitations": [
            "No git fetch or git push was performed.",
            "Remote-tracking refs may be stale; run git fetch yourself before relying on this result.",
            "This does not evaluate force-push policy, branch protection, CI, review approval, or requirements completion.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only pre-push safety check.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--branch")
    parser.add_argument("--remote-ref")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        report = build_report(args.repo, args.branch, args.remote_ref, args.require_clean)
    except GitInspectionError as exc:
        report = {
            "schema_version": "0.1.0",
            "tool": "check_push_readiness",
            "mode": "merge_push_check",
            "operation": "push",
            "verdict": "INVALID",
            "errors": [str(exc)],
        }
        write_json(report, args.output)
        return 2
    write_json(report, args.output)
    return exit_for_verdict(report["verdict"])


if __name__ == "__main__":
    sys.exit(main())
