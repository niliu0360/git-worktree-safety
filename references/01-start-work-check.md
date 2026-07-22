# 模式一：开始工作前检查

## 目标

在 AI、开发者或自动化工具开始修改仓库前，识别最常见的 Git 上下文错误。

## 检查顺序

1. 确认路径属于 Git working tree。
2. 确认 HEAD 不是 detached，除非任务明确要求在固定提交上做只读分析。
3. 确认当前分支与用户指定分支一致。
4. 检查 merge、rebase、cherry-pick、revert、bisect 或 sequencer 是否正在进行。
5. 检查 tracked 与 untracked 变更。
6. 检查当前分支是否有 upstream。
7. 读取 `git worktree list --porcelain`，标记当前 worktree 是否 locked。

## 判定

### SAFE_TO_WORK

- 当前路径是正常 Git worktree；
- HEAD 连接到本地分支；
- 没有未完成 Git 操作；
- 用户要求的严格条件均满足；
- 没有需要披露的警告。

### WORK_WITH_WARNINGS

常见情况：

- 工作区已有修改，但用户没有要求 `--require-clean`；
- 当前分支没有 upstream；
- worktree 被标记 locked；
- 其他不直接阻止编辑、但必须披露的状态。

已有改动可能属于用户或另一个会话。继续前应说明这些文件，并避免覆盖。

### DO_NOT_MODIFY

- detached HEAD；
- 当前分支与 `--expected-branch` 不一致；
- merge/rebase 等 Git 操作未结束；
- 启用 `--require-clean` 后仍有修改；
- 启用 `--require-upstream` 后没有 upstream。

## 不能自动判断的事项

`git worktree list` 不能证明目录当前没有被其他进程使用。0.1.0 不创建 PID 锁、不写 session registry，也不自动抢占 worktree。
