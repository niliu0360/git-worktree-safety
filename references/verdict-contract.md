# Verdict Contract

## 开始工作

| Verdict | 含义 |
|---|---|
| `SAFE_TO_WORK` | 未发现 Git 层面的阻止或警告。 |
| `WORK_WITH_WARNINGS` | 可以继续，但必须披露警告并避免覆盖既有工作。 |
| `DO_NOT_MODIFY` | 在解决阻止项前不要修改。 |
| `INVALID` | 输入或仓库状态无效。 |

## 合并

| Verdict | 含义 |
|---|---|
| `SAFE_TO_MERGE` | Git 检查通过；仍不代表需求、测试或评审通过。 |
| `MERGE_WITH_WARNINGS` | Git 没有硬阻止，但存在必须披露的风险。 |
| `DO_NOT_MERGE` | 冲突、脏 worktree、远端落后或 ref 问题阻止合并。 |
| `INVALID` | 输入或仓库状态无效。 |

## 推送

| Verdict | 含义 |
|---|---|
| `SAFE_TO_PUSH` | 本地分支领先且未落后本地 remote-tracking ref。 |
| `PUSH_WITH_WARNINGS` | 没有提交可推送、dirty 警告或其他非阻止项。 |
| `DO_NOT_PUSH` | 本地落后、缺少 remote ref、Git 操作进行中等。 |
| `INVALID` | 输入或仓库状态无效。 |

## 清理

| Verdict | 含义 |
|---|---|
| `SAFE_CANDIDATE` | Git 层面候选，仍需人工确认实际用途和活跃进程。 |
| `REVIEW_REQUIRED` | 需要人工判断，不能直接删。 |
| `DO_NOT_DELETE` | 明确不应删除。 |
