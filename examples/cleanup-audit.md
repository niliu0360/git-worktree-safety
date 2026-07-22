# 示例：清理旧 worktree

```bash
python scripts/list_cleanup_candidates.py \
  --repo . \
  --merged-into main \
  --idle-days 14 \
  --protect release
```

对 `SAFE_CANDIDATE`，仍需要人工确认目录不是部署、演示或长期调试环境。

对 `REVIEW_REQUIRED`，检查进程、编辑器、终端和任务记录。

对 `DO_NOT_DELETE`，不要使用 `--force` 绕过。先处理 dirty、未合并、locked、detached 或未完成 Git 操作。
