from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _control_adapter import to_control_adapter  # noqa: E402
from test_scripts import RepoFixture, script  # noqa: E402


class ControlAdapterTests(unittest.TestCase):
    def assert_schema_valid(self, value: dict) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads(
            (TESTS.parent / "schemas" / "adapter-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda error: list(error.absolute_path),
        )
        self.assertFalse(
            errors,
            "\n".join(
                f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
                for error in errors
            ),
        )

    def test_worktree_cli_emits_warn_adapter_and_preserves_exit_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gws-adapter-") as temp:
            fixture = RepoFixture(Path(temp))
            rc, value = script(
                "check_worktree.py",
                "--repo",
                str(fixture.repo),
                "--format",
                "control-adapter",
            )
            self.assertEqual(rc, 1)
            self.assertEqual(value["adapter_name"], "git-worktree-safety")
            self.assertEqual(value["check_type"], "WORKTREE_READINESS")
            self.assertEqual(value["scope"], "GIT_STATE_ONLY")
            self.assertEqual(value["result"], "WARN")
            self.assertEqual(value["legacy_verdict"], "WORK_WITH_WARNINGS")
            self.assertEqual(value["evidence_projection"], {"category": "git_state", "status": "WARN"})
            self.assertFalse(value["freshness"]["fetch_performed"])
            self.assertTrue(value["freshness"]["remote_state_may_be_stale"])
            self.assert_schema_valid(value)

    def test_invalid_cli_emits_unknown_adapter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gws-invalid-") as temp:
            rc, value = script(
                "check_worktree.py",
                "--repo",
                temp,
                "--format",
                "control-adapter",
            )
            self.assertEqual(rc, 2)
            self.assertEqual(value["result"], "UNKNOWN")
            self.assertEqual(value["legacy_verdict"], "INVALID")
            self.assertTrue(value["limitations"])
            self.assert_schema_valid(value)

    def test_block_verdict_maps_to_block_with_git_only_scope(self) -> None:
        value = to_control_adapter(
            {
                "tool": "check_merge_readiness",
                "verdict": "DO_NOT_MERGE",
                "repository_root": "/repo",
                "source": "feature/x",
                "target": "main",
                "source_oid": "abc123",
                "checks": [
                    {
                        "check": "merge_conflicts",
                        "status": "block",
                        "detail": "merge-tree reports conflicts",
                    }
                ],
                "blockers": [
                    {
                        "check": "merge_conflicts",
                        "detail": "merge-tree reports conflicts",
                    }
                ],
                "warnings": [],
                "limitations": ["No git fetch was performed."],
            }
        )
        self.assertEqual(value["check_type"], "MERGE_READINESS")
        self.assertEqual(value["result"], "BLOCK")
        self.assertTrue(value["blocking_items"])
        self.assertEqual(value["evidence_projection"]["status"], "FAIL")
        self.assert_schema_valid(value)

    def test_cleanup_batch_keeps_candidate_level_blocks_without_global_block(self) -> None:
        value = to_control_adapter(
            {
                "tool": "list_cleanup_candidates",
                "verdict": "AUDIT_COMPLETE_WITH_BLOCKED_ITEMS",
                "repository_root": "/repo",
                "merged_into": "main",
                "worktrees": [
                    {
                        "path": "/repo/wt-clean",
                        "branch": "feature/clean",
                        "verdict": "SAFE_CANDIDATE",
                        "merged_into_target": True,
                        "dirty": False,
                        "locked": False,
                        "age_days": 20,
                        "blockers": [],
                        "warnings": [],
                        "suggested_commands": [
                            "git worktree remove -- /repo/wt-clean",
                            "git branch -d -- feature/clean",
                        ],
                    },
                    {
                        "path": "/repo",
                        "branch": "main",
                        "verdict": "DO_NOT_DELETE",
                        "merged_into_target": True,
                        "dirty": False,
                        "locked": False,
                        "age_days": 20,
                        "blockers": ["protected branch: main"],
                        "warnings": [],
                        "suggested_commands": [],
                    },
                ],
                "limitations": ["Batch cleanup audit only."],
            }
        )
        self.assertEqual(value["check_type"], "CLEANUP_CANDIDATE")
        self.assertEqual(value["result"], "WARN")
        self.assertTrue(any(item["status"] == "BLOCK" for item in value["checks"]))
        self.assertTrue(any("protected branch" in item for item in value["blocking_items"]))
        self.assertTrue(any("worktree remove" in item for item in value["suggested_actions"]))
        self.assert_schema_valid(value)

    def test_default_output_remains_legacy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gws-legacy-") as temp:
            fixture = RepoFixture(Path(temp))
            rc, value = script("check_worktree.py", "--repo", str(fixture.repo))
            self.assertEqual(rc, 1)
            self.assertEqual(value["schema_version"], "0.1.0")
            self.assertIn("verdict", value)
            self.assertNotIn("adapter_result_id", value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
