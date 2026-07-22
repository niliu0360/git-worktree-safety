#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from _gitlib import (
    GitInspectionError,
    ahead_behind,
    default_branch,
    directory_age_days,
    ensure_repo,
    exit_for_verdict,
    is_ancestor,
    operation_in_progress,
    parse_worktrees,
    resolve_commit,
    status_porcelain,
    upstream_for,
    write_json,
)


def classify_worktree(
    invocation_root: Path,
    repo: Path,
    item: dict,
    target: str,
    idle_days: int,
    protected: set[str],
) -> dict:
    path = Path(str(item.get("worktree", ""))).resolve()
    branch = item.get("branch") if isinstance(item.get("branch"), str) else None
    reasons: list[str] = []
    warnings: list[str] = []
    status_entries: list[str] = []
    operations: list[str] = []
    age_days = directory_age_days(path)

    verdict = "SAFE_CANDIDATE"

    def block(reason: str) -> None:
        nonlocal verdict
        verdict = "DO_NOT_DELETE"
        reasons.append(reason)

    def review(reason: str) -> None:
        nonlocal verdict
        if verdict != "DO_NOT_DELETE":
            verdict = "REVIEW_REQUIRED"
        warnings.append(reason)

    if path == invocation_root:
        block("this is the worktree from which the audit is running")
    if item.get("locked") is not None:
        block("worktree is marked locked")
    if item.get("prunable") is not None or not path.exists():
        review("worktree path is missing or marked prunable; inspect Git metadata manually")
    if item.get("detached") is not None or not branch:
        block("detached worktree has no normal local branch")
    if branch and branch in protected:
        block(f"protected branch: {branch}")

    if path.exists():
        operations = operation_in_progress(path)
        status_entries = status_porcelain(path)
        if operations:
            block("Git operation in progress: " + ", ".join(operations))
        if status_entries:
            block(f"worktree contains {len(status_entries)} changed path(s)")

    merged = None
    if branch and resolve_commit(repo, branch) and resolve_commit(repo, target):
        merged = is_ancestor(repo, branch, target)
        if merged is False:
            block(f"branch {branch} is not merged into {target}")
        elif merged is None:
            review("could not determine merge ancestry")
    elif branch:
        block("branch or target ref cannot be resolved")

    upstream = upstream_for(repo, branch) if branch else None
    divergence = ahead_behind(repo, branch, upstream) if branch and upstream else None
    if not upstream and branch:
        warnings.append("branch has no configured upstream; this does not block worktree removal")

    if age_days is None:
        review("worktree age is unavailable")
    elif age_days < idle_days:
        review(f"worktree directory was modified {age_days:.1f} day(s) ago; threshold is {idle_days}")

    commands: list[str] = []
    if verdict == "SAFE_CANDIDATE" and branch:
        commands = [
            f"git worktree remove -- {shlex.quote(str(path))}",
            f"git branch -d -- {shlex.quote(branch)}",
        ]

    return {
        "path": str(path),
        "branch": branch,
        "head": item.get("HEAD"),
        "verdict": verdict,
        "merged_into_target": merged,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "locked": item.get("locked") is not None,
        "prunable": item.get("prunable") is not None,
        "operations_in_progress": operations,
        "dirty": bool(status_entries),
        "status_entries": status_entries,
        "upstream": upstream,
        "ahead": divergence[0] if divergence else None,
        "behind": divergence[1] if divergence else None,
        "blockers": reasons,
        "warnings": warnings,
        "suggested_commands": commands,
    }


def build_report(
    repo_arg: str,
    target: str | None,
    idle_days: int,
    extra_protected: list[str],
) -> dict:
    repo = ensure_repo(Path(repo_arg).resolve())
    target_branch = target or default_branch(repo)
    if not target_branch:
        raise GitInspectionError("cannot determine target branch; pass --merged-into")
    if not resolve_commit(repo, target_branch):
        raise GitInspectionError(f"target ref cannot be resolved: {target_branch}")

    protected = {target_branch, "main", "master", "trunk", *extra_protected}
    worktrees = [
        classify_worktree(repo, repo, item, target_branch, idle_days, protected)
        for item in parse_worktrees(repo)
    ]
    counts = {
        "SAFE_CANDIDATE": sum(1 for item in worktrees if item["verdict"] == "SAFE_CANDIDATE"),
        "REVIEW_REQUIRED": sum(1 for item in worktrees if item["verdict"] == "REVIEW_REQUIRED"),
        "DO_NOT_DELETE": sum(1 for item in worktrees if item["verdict"] == "DO_NOT_DELETE"),
    }
    if counts["DO_NOT_DELETE"]:
        overall = "AUDIT_COMPLETE_WITH_BLOCKED_ITEMS"
    elif counts["REVIEW_REQUIRED"]:
        overall = "AUDIT_COMPLETE_WITH_REVIEWS"
    else:
        overall = "AUDIT_COMPLETE"

    return {
        "schema_version": "0.1.0",
        "tool": "list_cleanup_candidates",
        "mode": "cleanup_audit",
        "verdict": overall,
        "repository_root": str(repo),
        "merged_into": target_branch,
        "idle_days": idle_days,
        "protected_branches": sorted(protected),
        "counts": counts,
        "worktrees": worktrees,
        "limitations": [
            "This command only audits and prints suggestions; it never removes a worktree or branch.",
            "Directory modification time is advisory and cannot prove that a process or AI session is inactive.",
            "SAFE_CANDIDATE means Git-level checks passed; human confirmation is still required before deletion.",
            "No git fetch was performed, so target and upstream refs may be stale.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of Git worktree cleanup candidates.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--merged-into", dest="target")
    parser.add_argument("--idle-days", type=int, default=7)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.idle_days < 0:
        parser.error("--idle-days must be >= 0")
    try:
        report = build_report(args.repo, args.target, args.idle_days, args.protect)
    except GitInspectionError as exc:
        report = {
            "schema_version": "0.1.0",
            "tool": "list_cleanup_candidates",
            "mode": "cleanup_audit",
            "verdict": "INVALID",
            "errors": [str(exc)],
        }
        write_json(report, args.output)
        return 2
    write_json(report, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
