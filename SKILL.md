---
name: git-worktree-safety
description: Use when AI Coding 任务涉及 Git worktree、多窗口或多 Agent 并行开发、开始修改仓库、合并分支、推送远端、删除旧 worktree 或清理分支，尤其是用户要求“确认能不能改”“检查是否安全合并”“清理 worktree”“避免多个会话互相覆盖”。通过只读 Git 检查给出安全结论；不要自动执行 merge、push、reset、stash、worktree remove 或 branch delete。
---

# Git Worktree Safety

本 Skill 用来回答三个问题：

1. **当前 worktree 现在适合继续修改吗？**
2. **当前分支适合合并或推送吗？**
3. **哪些旧 worktree 只是在 Git 层面具备清理条件？**

它检查 Git 状态，不判断用户需求是否已经完成。需求、Todo 和验证证据是否闭环，应使用 `completion-discipline`。

## 基本原则

- 默认只读，不执行任何改变仓库状态的命令。
- 不根据“看起来没人在用”直接删除 worktree。
- 不把“Git 可以合并”表述成“功能已经完成”。
- 不把目录修改时间当作会话所有权证据。
- 不隐式执行 `git fetch`；远端比较可能基于过期的 remote-tracking refs。
- 任何删除、合并、推送、重置和 stash，都必须由用户或上层工具显式执行。

## 模式一：开始工作前检查

适用于准备修改代码、切换到已有 worktree、多个 AI 会话并行开发，或用户询问当前目录能不能继续工作。

先运行：

```bash
python /path/to/git-worktree-safety/scripts/check_worktree.py --repo .
```

需要严格要求干净工作区或指定分支时：

```bash
python /path/to/git-worktree-safety/scripts/check_worktree.py \
  --repo . \
  --expected-branch feature/payment \
  --require-clean \
  --require-upstream
```

按脚本结果表述：

- `SAFE_TO_WORK`：没有发现 Git 层面的阻塞项。
- `WORK_WITH_WARNINGS`：可以继续，但必须先向用户披露已有改动、缺少 upstream 或其他警告。
- `DO_NOT_MODIFY`：detached HEAD、分支不符、merge/rebase 未结束，或严格条件未满足。
- `INVALID`：路径不是 Git worktree，或仓库状态无法读取。

即使结果为 `SAFE_TO_WORK`，也只能说明未发现 Git 元数据冲突，不能证明没有其他编辑器、进程或 AI 会话正在使用该目录。

完整规则见 `references/01-start-work-check.md`。

## 模式二：合并或推送前检查

### 合并检查

```bash
python /path/to/git-worktree-safety/scripts/check_merge_readiness.py \
  --repo . \
  --source feature/payment \
  --target main
```

可选严格条件：

```bash
python /path/to/git-worktree-safety/scripts/check_merge_readiness.py \
  --repo . \
  --source feature/payment \
  --target main \
  --require-source-pushed \
  --require-target-synced
```

结果：

- `SAFE_TO_MERGE`
- `MERGE_WITH_WARNINGS`
- `DO_NOT_MERGE`
- `INVALID`

### 推送检查

```bash
python /path/to/git-worktree-safety/scripts/check_push_readiness.py \
  --repo . \
  --branch main
```

结果：

- `SAFE_TO_PUSH`
- `PUSH_WITH_WARNINGS`
- `DO_NOT_PUSH`
- `INVALID`

脚本不会执行 `fetch`、`merge` 或 `push`。如果远端状态很重要，先由用户显式运行 `git fetch --prune`，再重新检查。

完整规则见 `references/02-merge-push-check.md`。

## 模式三：清理前审计

只生成 worktree 候选分类：

```bash
python /path/to/git-worktree-safety/scripts/list_cleanup_candidates.py \
  --repo . \
  --merged-into main \
  --idle-days 7
```

结果按每个 worktree 分类：

- `SAFE_CANDIDATE`：Git 层面的保守检查通过，但删除前仍需人工确认没有活跃进程或长期用途。
- `REVIEW_REQUIRED`：最近有活动、路径缺失、元数据异常，或存在无法自动判断的情况。
- `DO_NOT_DELETE`：脏工作区、未合并、受保护分支、锁定、detached HEAD 或 Git 操作进行中。

脚本只打印建议命令，不执行 `git worktree remove` 或 `git branch -d`。

完整规则见 `references/03-cleanup-audit.md`。

## 辅助仓库检查

需要先完整查看仓库、分支、upstream、dirty 状态和所有 worktree 时：

```bash
python /path/to/git-worktree-safety/scripts/inspect_repository.py --repo .
```

所有脚本输出 JSON，可以通过 `--output report.json` 同时落盘。默认检查不修改 Git refs、index、配置或已有文件；指定 `--output` 会创建或覆盖用户指定的报告文件。

## 不可违反的规则

1. 不自动执行 `git merge`、`git push`、`git reset`、`git stash`、`git checkout`、`git worktree remove` 或分支删除。
2. 不使用 `--force` 清理 worktree 或分支。
3. 不因为分支已合并，就忽略 dirty、untracked、locked、detached 或正在进行的 Git 操作。
4. 不把 remote-tracking ref 当作实时远端状态；未执行 fetch 时必须披露可能过期。
5. 不声称检测到了真实的“会话所有者”。Git 元数据不能证明某个目录无人使用。
6. `SAFE_TO_MERGE` 只代表 Git 检查没有发现阻塞，不代表测试通过、代码正确、需求完成或已获评审批准。
7. `SAFE_CANDIDATE` 不是自动删除许可，必须有人确认实际用途和活跃进程。
8. 脚本失败或检查不可用时，降级为警告或阻止，不得编造安全结论。

## 可选确定性脚本

| 脚本 | 用途 | 是否修改仓库 |
|---|---|---|
| `scripts/inspect_repository.py` | 汇总仓库、分支、upstream、dirty 和 worktree 状态 | 默认不修改；`--output` 写报告 |
| `scripts/check_worktree.py` | 开始工作前检查当前 worktree | 默认不修改；`--output` 写报告 |
| `scripts/check_merge_readiness.py` | 合并前检查 ancestry、冲突、worktree 和远端跟踪状态 | 默认不修改；`--output` 写报告 |
| `scripts/check_push_readiness.py` | 推送前检查本地分支与 remote-tracking ref 的分叉 | 默认不修改；`--output` 写报告 |
| `scripts/list_cleanup_candidates.py` | 清理前列出候选、阻止项和人工建议命令 | 默认不修改；`--output` 写报告 |

## 输出要求

对用户给出结论时，至少包含：

- verdict；
- 发现的阻止项；
- 需要披露的警告；
- 脚本没有检查或无法证明的边界；
- 下一步应由谁显式执行。

不要只说“安全”“没问题”或“可以删”。
