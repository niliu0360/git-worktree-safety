# 模式三：清理前审计

## 目标

列出 worktree 的 Git 层面清理候选，不自动执行删除。

## 每个 worktree 的检查

- 是否为当前执行审计的 worktree；
- 是否处于 locked 状态；
- 路径是否存在，是否被 Git 标记 prunable；
- 是否 detached HEAD；
- 分支是否属于受保护集合；
- 是否存在 dirty 或 untracked 文件；
- 是否存在 merge/rebase 等未完成操作；
- 分支是否已经合入 `--merged-into` 指定目标；
- 目录修改时间是否超过 `--idle-days`；
- upstream 与 ahead/behind，仅作为补充信息。

## 判定

### SAFE_CANDIDATE

满足所有保守 Git 条件，且目录修改时间超过阈值。脚本可以给出人工建议命令，但不会执行。

这不代表目录一定无人使用。删除前仍应确认：

- 没有运行中的编辑器、测试、服务或 AI 会话；
- worktree 不是部署目录、演示目录或长期保留目录；
- 用户接受删除本地分支。

### REVIEW_REQUIRED

- worktree 最近有目录活动；
- 路径缺失或 prunable；
- 无法判断年龄或其他非致命状态。

### DO_NOT_DELETE

- 当前审计 worktree；
- 受保护分支；
- locked；
- detached HEAD；
- dirty/untracked；
- 未合入目标；
- Git 操作进行中；
- ref 无法解析。

## 建议命令

脚本只对 `SAFE_CANDIDATE` 输出：

```bash
git worktree remove -- <path>
git branch -d -- <branch>
```

禁止自动改成 `--force` 或 `git branch -D`。
