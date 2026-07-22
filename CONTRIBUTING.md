# Contributing

Contributions are welcome during the Public Beta.

1. Open an issue describing the Git state and expected conservative verdict.
2. Preserve the default read-only boundary: no automatic fetch, merge, push, reset, stash, checkout, worktree removal, or branch deletion.
3. Treat unavailable checks as warnings or blockers, never as proof of safety.
4. Add regression coverage and run `bash tests/run_all.sh` before submitting a pull request.

Tests must use disposable repositories and must not mutate a contributor's real project.
