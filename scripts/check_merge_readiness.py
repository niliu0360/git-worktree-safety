#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _gitlib import (
    GitInspectionError,
    ahead_behind,
    branch_worktree,
    ensure_repo,
    exit_for_verdict,
    is_ancestor,
    merge_tree_check,
    operation_in_progress,
    resolve_commit,
    status_porcelain,
    upstream_for,
    write_json,
)


def build_report(
    repo_arg: str,
    source: str,
    target: str,
    require_source_pushed: bool,
    require_target_synced: bool,
) -> dict:
    repo = ensure_repo(Path(repo_arg).resolve())
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

    source_oid = resolve_commit(repo, source)
    target_oid = resolve_commit(repo, target)
    check("source_ref", "pass" if source_oid else "block", source_oid or f"unknown ref: {source}")
    check("target_ref", "pass" if target_oid else "block", target_oid or f"unknown ref: {target}")
    check(
        "distinct_refs",
        "pass" if source != target else "block",
        f"source={source}; target={target}",
    )

    source_wt = branch_worktree(repo, source)
    target_wt = branch_worktree(repo, target)
    for role, branch, item in (("source", source, source_wt), ("target", target, target_wt)):
        if not item:
            check(f"{role}_worktree", "pass", f"{branch} is not checked out in a linked worktree")
            continue
        wt_path = Path(str(item["worktree"]))
        operations = operation_in_progress(wt_path)
        dirty = status_porcelain(wt_path)
        check(
            f"{role}_git_operation",
            "block" if operations else "pass",
            ", ".join(operations) if operations else "none",
            {"worktree": str(wt_path)},
        )
        check(
            f"{role}_worktree_clean",
            "block" if dirty else "pass",
            f"{len(dirty)} changed path(s)" if dirty else "clean",
            {"worktree": str(wt_path), "status_entries": dirty},
        )
        if item.get("locked") is not None:
            check(
                f"{role}_worktree_locked",
                "warn",
                "worktree is marked locked",
                {"worktree": str(wt_path)},
            )

    if source_oid and target_oid:
        already_merged = is_ancestor(repo, source, target)
        check(
            "already_merged",
            "warn" if already_merged else "pass",
            f"{source} is already reachable from {target}" if already_merged else "source is not already merged",
        )
        target_in_source = is_ancestor(repo, target, source)
        check(
            "target_ancestry",
            "pass" if target_in_source else "warn",
            f"{target} is an ancestor of {source}" if target_in_source else f"{source} does not contain the current {target}",
        )
        merge_tree = merge_tree_check(repo, target, source)
        if merge_tree["available"]:
            check(
                "merge_conflicts",
                "pass" if merge_tree["clean"] else "block",
                "read-only merge-tree check is clean" if merge_tree["clean"] else "merge-tree reports conflicts",
                {"messages": merge_tree["messages"]},
            )
        else:
            check(
                "merge_conflicts",
                "warn",
                "merge-tree conflict check unavailable on this Git version",
                {"messages": merge_tree["messages"]},
            )

    source_upstream = upstream_for(repo, source)
    if source_upstream:
        divergence = ahead_behind(repo, source, source_upstream)
        ahead, behind = divergence if divergence else (None, None)
        status = "pass"
        if ahead and require_source_pushed:
            status = "block"
        elif ahead:
            status = "warn"
        if behind:
            status = "warn" if status != "block" else status
        check(
            "source_remote_state",
            status,
            f"upstream={source_upstream}; ahead={ahead}; behind={behind}",
        )
    else:
        check(
            "source_remote_state",
            "block" if require_source_pushed else "warn",
            "source branch has no configured upstream",
        )

    target_upstream = upstream_for(repo, target)
    if target_upstream:
        divergence = ahead_behind(repo, target, target_upstream)
        ahead, behind = divergence if divergence else (None, None)
        if behind:
            status = "block"
        elif ahead:
            status = "warn"
        else:
            status = "pass"
        check(
            "target_remote_state",
            status,
            f"upstream={target_upstream}; ahead={ahead}; behind={behind}",
        )
    else:
        check(
            "target_remote_state",
            "block" if require_target_synced else "warn",
            "target branch has no configured upstream",
        )

    if blockers:
        verdict = "DO_NOT_MERGE"
    elif warnings:
        verdict = "MERGE_WITH_WARNINGS"
    else:
        verdict = "SAFE_TO_MERGE"

    return {
        "schema_version": "0.1.0",
        "tool": "check_merge_readiness",
        "mode": "merge_push_check",
        "operation": "merge",
        "verdict": verdict,
        "repository_root": str(repo),
        "source": source,
        "target": target,
        "source_oid": source_oid,
        "target_oid": target_oid,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "limitations": [
            "No repository ref, index, worktree, or configuration was modified; merge-tree objects are isolated in a temporary object store.",
            "Remote-tracking refs may be stale; run git fetch yourself before relying on remote comparisons.",
            "This checks Git safety only, not tests, requirements, review approval, or deployment readiness.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only pre-merge safety check.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--require-source-pushed", action="store_true")
    parser.add_argument("--require-target-synced", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        report = build_report(
            args.repo,
            args.source,
            args.target,
            args.require_source_pushed,
            args.require_target_synced,
        )
    except GitInspectionError as exc:
        report = {
            "schema_version": "0.1.0",
            "tool": "check_merge_readiness",
            "mode": "merge_push_check",
            "operation": "merge",
            "verdict": "INVALID",
            "errors": [str(exc)],
        }
        write_json(report, args.output)
        return 2
    write_json(report, args.output)
    return exit_for_verdict(report["verdict"])


if __name__ == "__main__":
    sys.exit(main())
