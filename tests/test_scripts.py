#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_script_module(filename: str):
    module_name = f"test_{Path(filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args], check=check)


def script(name: str, *args: str) -> tuple[int, dict]:
    proc = run([sys.executable, str(SCRIPTS / name), *args], check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON from {name}: {proc.stdout}\n{proc.stderr}") from exc
    return proc.returncode, payload


class RepoFixture:
    def __init__(self, base: Path, with_remote: bool = False):
        self.base = base
        self.remote = base / "remote.git"
        self.repo = base / "repo"
        if with_remote:
            run(["git", "init", "--bare", "-q", str(self.remote)])
            run(["git", "clone", "-q", str(self.remote), str(self.repo)])
            git(self.repo, "switch", "-c", "main")
        else:
            run(["git", "init", "-q", "-b", "main", str(self.repo)])
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test User")
        (self.repo / "file.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "file.txt")
        git(self.repo, "commit", "-qm", "base")
        if with_remote:
            git(self.repo, "push", "-qu", "origin", "main")
            run(["git", "--git-dir", str(self.remote), "symbolic-ref", "HEAD", "refs/heads/main"])

    def create_feature(self, name: str = "feature/test", push: bool = False) -> None:
        git(self.repo, "switch", "-qc", name)
        with (self.repo / "file.txt").open("a", encoding="utf-8") as fh:
            fh.write(f"{name}\n")
        git(self.repo, "commit", "-qam", name)
        if push:
            git(self.repo, "push", "-qu", "origin", name)
        git(self.repo, "switch", "-q", "main")


class GitWorktreeSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gws-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_non_git_is_invalid(self) -> None:
        rc, data = script("check_worktree.py", "--repo", str(self.tmp))
        self.assertEqual(rc, 2)
        self.assertEqual(data["verdict"], "INVALID")

    def test_clean_repo_without_upstream_warns(self) -> None:
        fx = RepoFixture(self.tmp)
        rc, data = script("check_worktree.py", "--repo", str(fx.repo))
        self.assertEqual(rc, 1)
        self.assertEqual(data["verdict"], "WORK_WITH_WARNINGS")
        self.assertTrue(any(x["check"] == "upstream" for x in data["warnings"]))

    def test_dirty_repo_can_warn_or_block(self) -> None:
        fx = RepoFixture(self.tmp)
        (fx.repo / "file.txt").write_text("changed\n", encoding="utf-8")
        rc, data = script("check_worktree.py", "--repo", str(fx.repo))
        self.assertEqual((rc, data["verdict"]), (1, "WORK_WITH_WARNINGS"))
        rc, data = script("check_worktree.py", "--repo", str(fx.repo), "--require-clean")
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_MODIFY"))

    def test_detached_head_blocks(self) -> None:
        fx = RepoFixture(self.tmp)
        git(fx.repo, "checkout", "-q", "--detach", "HEAD")
        rc, data = script("check_worktree.py", "--repo", str(fx.repo))
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_MODIFY"))

    def test_expected_branch_mismatch_blocks(self) -> None:
        fx = RepoFixture(self.tmp)
        rc, data = script(
            "check_worktree.py",
            "--repo",
            str(fx.repo),
            "--expected-branch",
            "feature/other",
        )
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_MODIFY"))

    def test_clean_merge_with_synced_upstreams_is_safe(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        fx.create_feature(push=True)
        rc, data = script(
            "check_merge_readiness.py",
            "--repo",
            str(fx.repo),
            "--source",
            "feature/test",
            "--target",
            "main",
            "--require-source-pushed",
            "--require-target-synced",
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data["verdict"], "SAFE_TO_MERGE")

    def test_merge_conflict_blocks(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        git(fx.repo, "switch", "-qc", "feature/conflict")
        (fx.repo / "file.txt").write_text("feature\n", encoding="utf-8")
        git(fx.repo, "commit", "-qam", "feature conflict")
        git(fx.repo, "push", "-qu", "origin", "feature/conflict")
        git(fx.repo, "switch", "-q", "main")
        (fx.repo / "file.txt").write_text("main\n", encoding="utf-8")
        git(fx.repo, "commit", "-qam", "main conflict")
        git(fx.repo, "push", "-q")
        rc, data = script(
            "check_merge_readiness.py",
            "--repo",
            str(fx.repo),
            "--source",
            "feature/conflict",
            "--target",
            "main",
        )
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_MERGE"))
        self.assertTrue(any(x["check"] == "merge_conflicts" for x in data["blockers"]))

    def test_target_behind_remote_blocks_merge(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        fx.create_feature(push=True)
        other = self.tmp / "other"
        run(["git", "clone", "-q", str(fx.remote), str(other)])
        git(other, "config", "user.email", "test@example.com")
        git(other, "config", "user.name", "Other")
        (other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(other, "add", "remote.txt")
        git(other, "commit", "-qm", "remote update")
        git(other, "push", "-q")
        git(fx.repo, "fetch", "-q", "origin")
        rc, data = script(
            "check_merge_readiness.py",
            "--repo",
            str(fx.repo),
            "--source",
            "feature/test",
            "--target",
            "main",
        )
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_MERGE"))
        self.assertTrue(any(x["check"] == "target_remote_state" for x in data["blockers"]))

    def test_push_readiness_safe_when_ahead(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        git(fx.repo, "switch", "-qc", "feature/push")
        git(fx.repo, "push", "-qu", "origin", "feature/push")
        (fx.repo / "push.txt").write_text("local\n", encoding="utf-8")
        git(fx.repo, "add", "push.txt")
        git(fx.repo, "commit", "-qm", "local commit")
        rc, data = script(
            "check_push_readiness.py", "--repo", str(fx.repo), "--branch", "feature/push"
        )
        self.assertEqual((rc, data["verdict"]), (0, "SAFE_TO_PUSH"))

    def test_push_behind_blocks(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        other = self.tmp / "other"
        run(["git", "clone", "-q", str(fx.remote), str(other)])
        git(other, "config", "user.email", "test@example.com")
        git(other, "config", "user.name", "Other")
        (other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(other, "add", "remote.txt")
        git(other, "commit", "-qm", "remote update")
        git(other, "push", "-q")
        git(fx.repo, "fetch", "-q", "origin")
        rc, data = script("check_push_readiness.py", "--repo", str(fx.repo), "--branch", "main")
        self.assertEqual((rc, data["verdict"]), (2, "DO_NOT_PUSH"))

    def test_push_divergence_unavailable_blocks(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        module = load_script_module("check_push_readiness.py")
        with mock.patch.object(module, "ahead_behind", return_value=None):
            data = module.build_report(str(fx.repo), "main", None, False)
        self.assertEqual(data["verdict"], "DO_NOT_PUSH")
        issue = next(x for x in data["blockers"] if x["check"] == "remote_divergence")
        self.assertIn("unable to determine", issue["detail"])

    def test_merge_divergence_unavailable_warns_or_blocks(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        fx.create_feature(push=True)
        module = load_script_module("check_merge_readiness.py")
        with mock.patch.object(module, "ahead_behind", return_value=None):
            relaxed = module.build_report(str(fx.repo), "feature/test", "main", False, False)
            strict = module.build_report(str(fx.repo), "feature/test", "main", False, True)
        self.assertEqual(relaxed["verdict"], "MERGE_WITH_WARNINGS")
        self.assertTrue(any("unable to determine" in x["detail"] for x in relaxed["warnings"]))
        self.assertEqual(strict["verdict"], "DO_NOT_MERGE")

    def test_output_path_writes_report_file(self) -> None:
        fx = RepoFixture(self.tmp)
        output = fx.repo / "safety-report.json"
        rc, data = script("inspect_repository.py", "--repo", str(fx.repo), "--output", str(output))
        self.assertEqual(rc, 0)
        self.assertTrue(output.is_file())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["tool"], data["tool"])
        self.assertIn("?? safety-report.json", git(fx.repo, "status", "--porcelain=v1").stdout)

    def test_bare_repository_is_invalid(self) -> None:
        bare = self.tmp / "bare.git"
        run(["git", "init", "--bare", "-q", str(bare)])
        rc, data = script("check_worktree.py", "--repo", str(bare))
        self.assertEqual((rc, data["verdict"]), (2, "INVALID"))

    def test_shallow_clone_is_inspectable(self) -> None:
        fx = RepoFixture(self.tmp / "source", with_remote=True)
        shallow = self.tmp / "shallow"
        run(["git", "clone", "-q", "--depth", "1", fx.remote.as_uri(), str(shallow)])
        rc, data = script("inspect_repository.py", "--repo", str(shallow))
        self.assertEqual(rc, 0)
        self.assertEqual(data["current_branch"], "main")

    def test_remote_name_other_than_origin(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        git(fx.repo, "remote", "rename", "origin", "upstream")
        rc, data = script("check_push_readiness.py", "--repo", str(fx.repo), "--branch", "main")
        self.assertEqual(rc, 1)
        remote_check = next(x for x in data["checks"] if x["check"] == "remote_ref")
        self.assertEqual(remote_check["detail"], "upstream/main")

    def test_cleanup_classifies_safe_dirty_and_current(self) -> None:
        fx = RepoFixture(self.tmp)
        fx.create_feature("feature/clean")
        clean_wt = self.tmp / "wt-clean"
        git(fx.repo, "worktree", "add", "-q", str(clean_wt), "feature/clean")
        git(fx.repo, "merge", "-q", "--no-ff", "feature/clean", "-m", "merge clean")
        old = time.time() - 20 * 86400
        os.utime(clean_wt, (old, old))

        git(fx.repo, "switch", "-qc", "feature/dirty")
        (fx.repo / "dirty-base.txt").write_text("base\n", encoding="utf-8")
        git(fx.repo, "add", "dirty-base.txt")
        git(fx.repo, "commit", "-qm", "dirty branch")
        git(fx.repo, "switch", "-q", "main")
        dirty_wt = self.tmp / "wt-dirty"
        git(fx.repo, "worktree", "add", "-q", str(dirty_wt), "feature/dirty")
        git(fx.repo, "merge", "-q", "--no-ff", "feature/dirty", "-m", "merge dirty")
        (dirty_wt / "untracked.txt").write_text("do not delete\n", encoding="utf-8")
        os.utime(dirty_wt, (old, old))

        rc, data = script(
            "list_cleanup_candidates.py",
            "--repo",
            str(fx.repo),
            "--merged-into",
            "main",
            "--idle-days",
            "7",
        )
        self.assertEqual(rc, 0)
        by_branch = {item.get("branch"): item for item in data["worktrees"]}
        self.assertEqual(by_branch["feature/clean"]["verdict"], "SAFE_CANDIDATE")
        self.assertEqual(by_branch["feature/dirty"]["verdict"], "DO_NOT_DELETE")
        self.assertEqual(by_branch["main"]["verdict"], "DO_NOT_DELETE")
        self.assertTrue(by_branch["feature/clean"]["suggested_commands"])
        self.assertFalse(by_branch["feature/dirty"]["suggested_commands"])
        self.assertTrue(dirty_wt.exists(), "audit must not remove dirty worktree")

    def test_cleanup_recent_candidate_requires_review(self) -> None:
        fx = RepoFixture(self.tmp)
        fx.create_feature("feature/recent")
        wt = self.tmp / "wt-recent"
        git(fx.repo, "worktree", "add", "-q", str(wt), "feature/recent")
        git(fx.repo, "merge", "-q", "--no-ff", "feature/recent", "-m", "merge recent")
        rc, data = script(
            "list_cleanup_candidates.py",
            "--repo",
            str(fx.repo),
            "--merged-into",
            "main",
            "--idle-days",
            "7",
        )
        self.assertEqual(rc, 0)
        item = next(x for x in data["worktrees"] if x.get("branch") == "feature/recent")
        self.assertEqual(item["verdict"], "REVIEW_REQUIRED")

    def test_checks_do_not_mutate_repository(self) -> None:
        fx = RepoFixture(self.tmp, with_remote=True)
        fx.create_feature(push=True)
        before_status = git(fx.repo, "status", "--porcelain=v1").stdout
        before_refs = git(fx.repo, "show-ref").stdout
        before_worktrees = git(fx.repo, "worktree", "list", "--porcelain").stdout
        common_dir_raw = git(fx.repo, "rev-parse", "--git-common-dir").stdout.strip()
        common_dir = Path(common_dir_raw)
        if not common_dir.is_absolute():
            common_dir = fx.repo / common_dir
        object_dir = common_dir.resolve() / "objects"
        before_objects = sorted(
            str(path.relative_to(object_dir)) for path in object_dir.rglob("*") if path.is_file()
        )
        script("inspect_repository.py", "--repo", str(fx.repo))
        script("check_worktree.py", "--repo", str(fx.repo))
        script(
            "check_merge_readiness.py",
            "--repo",
            str(fx.repo),
            "--source",
            "feature/test",
            "--target",
            "main",
        )
        script("check_push_readiness.py", "--repo", str(fx.repo), "--branch", "main")
        script("list_cleanup_candidates.py", "--repo", str(fx.repo), "--merged-into", "main")
        self.assertEqual(git(fx.repo, "status", "--porcelain=v1").stdout, before_status)
        self.assertEqual(git(fx.repo, "show-ref").stdout, before_refs)
        self.assertEqual(git(fx.repo, "worktree", "list", "--porcelain").stdout, before_worktrees)
        after_objects = sorted(
            str(path.relative_to(object_dir)) for path in object_dir.rglob("*") if path.is_file()
        )
        self.assertEqual(after_objects, before_objects, "checks must not add objects to source repository")

    def test_public_package_has_no_private_environment_residue(self) -> None:
        forbidden = ["/home/" + "ubuntu", "lending-" + "recon", "lending-" + "core", "baf" + "fle", "127.0.0.1:" + "7777"]
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        for token in forbidden:
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
