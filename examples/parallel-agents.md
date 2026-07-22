# 示例：两个 AI 会话准备修改同一项目

用户要求会话 B 继续处理 `feature/payment`。

```bash
python scripts/check_worktree.py \
  --repo /workspace/project-payment \
  --expected-branch feature/payment \
  --require-clean
```

若返回 `WORK_WITH_WARNINGS` 并列出已有改动，应先向用户说明具体文件，确认这些改动属于当前任务还是其他会话。

若返回 `DO_NOT_MODIFY`，不要为了继续任务而自动 reset、stash 或 checkout。

即使返回 `SAFE_TO_WORK`，也仍需确认会话 A 是否正在运行，因为 Git 不保存 AI 会话所有权。
