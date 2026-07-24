#!/usr/bin/env python3
"""Project legacy Git safety reports into the AICR 0.2 Adapter Result contract."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()

CHECK_TYPES = {
    "inspect_repository": "REPOSITORY_INSPECTION",
    "check_worktree": "WORKTREE_READINESS",
    "check_merge_readiness": "MERGE_READINESS",
    "check_push_readiness": "PUSH_READINESS",
    "list_cleanup_candidates": "CLEANUP_CANDIDATE",
}

PASS_VERDICTS = {
    "INSPECTED",
    "SAFE_TO_WORK",
    "SAFE_TO_MERGE",
    "SAFE_TO_PUSH",
    "AUDIT_COMPLETE",
}
WARN_VERDICTS = {
    "INSPECTED_WITH_WARNINGS",
    "WORK_WITH_WARNINGS",
    "MERGE_WITH_WARNINGS",
    "PUSH_WITH_WARNINGS",
    "AUDIT_COMPLETE_WITH_REVIEWS",
    # Cleanup is a batch inventory. Blocked candidates do not mean every candidate is blocked.
    "AUDIT_COMPLETE_WITH_BLOCKED_ITEMS",
}
BLOCK_VERDICTS = {
    "DO_NOT_MODIFY",
    "DO_NOT_MERGE",
    "DO_NOT_PUSH",
    "DO_NOT_DELETE",
}

STATUS_MAP = {
    "pass": "PASS",
    "warn": "WARN",
    "block": "BLOCK",
    "unknown": "UNKNOWN",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _issue_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value)
    name = value.get("check") or value.get("name") or value.get("branch") or value.get("path")
    detail = value.get("detail") or value.get("summary") or value.get("reason")
    if name and detail:
        return f"{name}: {detail}"
    if detail:
        return str(detail)
    return str(name or value)


def _texts(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_issue_text(value) for value in values if _issue_text(value).strip()]


def _legacy_result(verdict: str) -> str:
    if verdict in PASS_VERDICTS:
        return "PASS"
    if verdict in WARN_VERDICTS:
        return "WARN"
    if verdict in BLOCK_VERDICTS or verdict.startswith("DO_NOT_"):
        return "BLOCK"
    return "UNKNOWN"


def _legacy_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(report.get("checks", []), start=1):
        if not isinstance(item, dict):
            continue
        status = STATUS_MAP.get(str(item.get("status", "unknown")).lower(), "UNKNOWN")
        row: dict[str, Any] = {
            "check_id": str(item.get("check") or f"legacy-check-{index}"),
            "status": status,
            "summary": str(item.get("detail") or "Legacy Git safety check."),
        }
        if "data" in item:
            row["details"] = item["data"]
        checks.append(row)
    return checks


def _inspection_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("tool") != "inspect_repository":
        return []
    return [
        {
            "check_id": "repository-head",
            "status": "WARN" if report.get("detached_head") else "PASS",
            "summary": "HEAD is detached" if report.get("detached_head") else f"Current branch is {report.get('current_branch')}",
            "details": {"head_oid": report.get("head")},
        },
        {
            "check_id": "working-tree-cleanliness",
            "status": "WARN" if report.get("dirty") else "PASS",
            "summary": f"{len(report.get('status_entries', []))} changed path(s)" if report.get("dirty") else "Working tree is clean",
            "details": {"status_entries": report.get("status_entries", [])},
        },
        {
            "check_id": "git-operation",
            "status": "WARN" if report.get("operations_in_progress") else "PASS",
            "summary": ", ".join(report.get("operations_in_progress", [])) if report.get("operations_in_progress") else "No Git operation is in progress",
        },
        {
            "check_id": "upstream",
            "status": "PASS" if report.get("upstream") else "WARN",
            "summary": str(report.get("upstream") or "No configured upstream"),
        },
    ]


def _cleanup_checks(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    if report.get("tool") != "list_cleanup_candidates":
        return checks, blockers, warnings, actions
    for index, item in enumerate(report.get("worktrees", []), start=1):
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict") or "INVALID")
        status = {
            "SAFE_CANDIDATE": "PASS",
            "REVIEW_REQUIRED": "WARN",
            "DO_NOT_DELETE": "BLOCK",
        }.get(verdict, "UNKNOWN")
        branch = str(item.get("branch") or "<detached>")
        path = str(item.get("path") or "<unknown>")
        summary = f"{branch} at {path}: {verdict}"
        checks.append({
            "check_id": f"cleanup-candidate-{index}",
            "status": status,
            "summary": summary,
            "details": {
                "branch": item.get("branch"),
                "worktree": item.get("path"),
                "merged_into_target": item.get("merged_into_target"),
                "dirty": item.get("dirty"),
                "locked": item.get("locked"),
                "age_days": item.get("age_days"),
            },
        })
        blockers.extend(f"{branch}: {text}" for text in _texts(item.get("blockers")))
        warnings.extend(f"{branch}: {text}" for text in _texts(item.get("warnings")))
        actions.extend(str(command) for command in item.get("suggested_commands", []) if command)
    return checks, blockers, warnings, actions


def _subject(report: dict[str, Any]) -> dict[str, str]:
    repository = str(report.get("repository_root") or "unknown/repository")
    subject: dict[str, str] = {"repository": repository}
    tool = report.get("tool")
    if tool in {"inspect_repository", "check_worktree"}:
        subject["worktree"] = repository
    branch = report.get("current_branch") or report.get("branch")
    if isinstance(branch, str) and branch:
        subject["branch"] = branch
    source = report.get("source")
    target = report.get("target") or report.get("merged_into")
    if isinstance(source, str) and source:
        subject["source_ref"] = source
    if isinstance(target, str) and target:
        subject["target_ref"] = target
    head = report.get("head") or report.get("source_oid")
    if isinstance(head, str) and head:
        subject["head_oid"] = head
    return subject


def _remote_ref(report: dict[str, Any]) -> Optional[str]:
    for key in ("remote_ref", "upstream"):
        value = report.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def to_control_adapter(report: dict[str, Any]) -> dict[str, Any]:
    tool = str(report.get("tool") or "unknown")
    verdict = str(report.get("verdict") or "INVALID")
    result = _legacy_result(verdict)
    token = uuid.uuid4().hex

    checks = _legacy_checks(report)
    checks.extend(_inspection_checks(report))
    cleanup_checks, cleanup_blockers, cleanup_warnings, cleanup_actions = _cleanup_checks(report)
    checks.extend(cleanup_checks)

    blockers = [*_texts(report.get("blockers")), *cleanup_blockers]
    warnings = [*_texts(report.get("warnings")), *cleanup_warnings]
    limitations = _texts(report.get("limitations"))
    errors = _texts(report.get("errors"))
    if errors:
        result = "UNKNOWN"
        limitations.extend(errors)
        checks.append({
            "check_id": "adapter-input",
            "status": "UNKNOWN",
            "summary": "; ".join(errors),
        })

    # A batch cleanup inventory may contain blocked candidates and safe candidates together.
    # Keep its aggregate result as WARN while preserving candidate-level BLOCK checks.
    if tool == "list_cleanup_candidates" and verdict == "AUDIT_COMPLETE_WITH_BLOCKED_ITEMS":
        result = "WARN"

    if result == "BLOCK" and not blockers:
        blockers.append(f"Legacy Git safety verdict is {verdict}.")
    if result == "UNKNOWN" and not limitations:
        limitations.append("The Git state could not be classified safely from the legacy report.")

    if "This adapter reports Git state only and does not authorize merge, push, release, or cleanup." not in limitations:
        limitations.append(
            "This adapter reports Git state only and does not authorize merge, push, release, or cleanup."
        )

    suggested_actions = list(dict.fromkeys(cleanup_actions))
    if result in {"WARN", "BLOCK", "UNKNOWN"}:
        suggested_actions.append("Resolve or explicitly accept the reported Git-state issues, then rerun this check.")
    if tool in {"check_merge_readiness", "check_push_readiness", "inspect_repository"}:
        suggested_actions.append("Run git fetch --prune explicitly when fresh remote state is required, then rerun the check.")
    suggested_actions = list(dict.fromkeys(suggested_actions))

    remote_ref = _remote_ref(report)
    freshness: dict[str, Any] = {
        "fetch_performed": False,
        "remote_state_may_be_stale": True,
    }
    if remote_ref:
        freshness["remote_tracking_ref_observed"] = remote_ref

    projection_status = {
        "PASS": "PASS",
        "WARN": "WARN",
        "BLOCK": "FAIL",
        "UNKNOWN": "INCONCLUSIVE",
    }[result]

    return {
        "adapter_result_id": f"ADP-gws-{token[:16]}",
        "adapter_name": "git-worktree-safety",
        "adapter_version": VERSION,
        "run_id": f"gws-{token}",
        "observed_at": utc_now(),
        "check_type": CHECK_TYPES.get(tool, "REPOSITORY_INSPECTION"),
        "scope": "GIT_STATE_ONLY",
        "result": result,
        "subject": _subject(report),
        "checks": checks,
        "blocking_items": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": list(dict.fromkeys(limitations)),
        "freshness": freshness,
        "suggested_actions": suggested_actions,
        "legacy_verdict": verdict,
        "evidence_projection": {
            "category": "git_state",
            "status": projection_status,
        },
    }


def format_report(report: dict[str, Any], output_format: str) -> dict[str, Any]:
    if output_format == "legacy":
        return report
    if output_format == "control-adapter":
        return to_control_adapter(report)
    raise ValueError(f"unknown output format: {output_format}")


def add_format_argument(parser: Any) -> None:
    parser.add_argument(
        "--format",
        choices=("legacy", "control-adapter"),
        default="legacy",
        help="Output the existing 0.1 report or an AICR 0.2 GIT_STATE_ONLY Adapter Result.",
    )
