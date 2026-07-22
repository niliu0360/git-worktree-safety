# 示例：合并功能分支到 main

先由用户显式刷新远端：

```bash
git fetch --prune
```

再检查：

```bash
python scripts/check_merge_readiness.py \
  --repo . \
  --source feature/payment \
  --target main \
  --require-target-synced
```

`SAFE_TO_MERGE` 只表示 Git 层面没有发现脏 worktree、目标落后或 merge-tree 冲突。

仍应另外检查：

- completion-discipline 是否为 `COMPLETE` 或已明确披露例外；
- 测试是否真实执行；
- PR 审批和 CI 是否通过；
- 部署或数据库变更是否已评审。
