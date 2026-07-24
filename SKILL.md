---
name: git-worktree-safety
description: Use when AI Coding 任务涉及 Git worktree、多窗口或多 Agent 并行开发、开始修改仓库、合并分支、推送远端、删除旧 worktree 或清理分支，尤其是用户要求“确认能不能改”“检查是否安全合并”“清理 worktree”“避免多个会话互相覆盖”。通过只读 Git 检查给出安全结论；不要自动执行 merge、push、reset、stash、worktree remove 或 branch delete。
---

# Git Worktree Safety

本 Skill 用来回答三个问题：

1. **当前 worktree 现在适合继续修改吗？**
2. **当前分支具备哪些 Git 层面的合并或推送条件？**
3. **哪些旧 worktree 只是在 Git 层面具备清理候选条件？**

它检查 Git 状态，不判断用户需求是否已经完成，也不独立授权合并、推送、发布或删除。

## 基本原则

- 默认只读，不执行任何改变仓库状态的命令。
- 不根据“看起来没人在用”直接删除 worktree。
- 不把“Git 可以合并”表述成“功能已经完成”。
- 不把目录修改时间当作会话所有权证据。
- 不隐式执行 `git fetch`；远端比较可能基于过期的 remote-tracking refs。
- 任何删除、合并、推送、重置和 stash，都必须由用户或上层工具显式执行。
- 作为 Control Layer Adapter 时，固定声明 `scope: GIT_STATE_ONLY`。

## 输出模式

默认保持 0.1.x JSON：

```text
--format legacy
```

需要接入 `ai-engineering-control-layer` 时使用：

```text
--format control-adapter
```

Control Adapter 输出：

- `result`: `PASS / WARN / BLOCK / UNKNOWN`
- `scope`: `GIT_STATE_ONLY`
- `check_type`: `WORKTREE_READINESS / MERGE_READINESS / PUSH_READINESS / CLEANUP_CANDIDATE / REPOSITORY_INSPECTION`
- 检查明细、阻止项、警告、限制、freshness 和建议动作
- `legacy_verdict` 兼容字段
- 可写入 Evidence Ledger 的 `git_state` 投影

这只是 Adapter Result，不是 Policy Decision。上层必须结合 Acceptance Contract、Risk、其他 Evidence 和审批要求重新判断。

## 模式一：开始工作前检查

适用于准备修改代码、切换到已有 worktree、多个 AI 会话并行开发，或用户询问当前目录能不能继续工作。

```bash
python /path/to/git-worktree-safety/scripts/check_worktree.py --repo .
```

严格要求：

```bash
python /path/to/git-worktree-safety/scripts/check_worktree.py \
  --repo . \
  --expected-branch feature/payment \
  --require-clean \
  --require-upstream
```

旧格式结果：

- `SAFE_TO_WORK`
- `WORK_WITH_WARNINGS`
- `DO_NOT_MODIFY`
- `INVALID`

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

旧格式结果：

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

旧格式结果：

- `SAFE_TO_PUSH`
- `PUSH_WITH_WARNINGS`
- `DO_NOT_PUSH`
- `INVALID`

脚本不会执行 `fetch`、`merge` 或 `push`。如果远端状态很重要，先由用户显式运行 `git fetch --prune`，再重新检查。

完整规则见 `references/02-merge-push-check.md`。

## 模式三：清理前审计

```bash
python /path/to/git-worktree-safety/scripts/list_cleanup_candidates.py \
  --repo . \
  --merged-into main \
  --idle-days 7
```

旧格式按每个 worktree 分类：

- `SAFE_CANDIDATE`：Git 层面的保守检查通过，但删除前仍需人工确认没有活跃进程或长期用途。
- `REVIEW_REQUIRED`：最近有活动、路径缺失、元数据异常，或存在无法自动判断的情况。
- `DO_NOT_DELETE`：脏工作区、未合并、受保护分支、锁定、detached HEAD 或 Git 操作进行中。

Control Adapter 会保留每个候选的独立 PASS/WARN/BLOCK check。批量结果出现受保护或脏 worktree 时使用 `WARN`，不能据此批量删除；只允许人工选择明确的安全候选。

脚本只打印建议命令，不执行 `git worktree remove` 或 `git branch -d`。

完整规则见 `references/03-cleanup-audit.md`。

## 辅助仓库检查

```bash
python /path/to/git-worktree-safety/scripts/inspect_repository.py --repo .
```

所有脚本输出 JSON，可以通过 `--output report.json` 同时落盘。默认检查不修改 Git refs、index、配置或已有文件；指定 `--output` 会创建或覆盖用户指定的报告文件。

## Control Layer 接入示例

```bash
python /path/to/git-worktree-safety/scripts/check_merge_readiness.py \
  --repo . \
  --source feature/payment \
  --target main \
  --format control-adapter \
  --output .ai-control/adapters/git-merge.json
```

然后由 Control Layer 导入 Adapter Result。不得把 `PASS` 直接改写成 `ALLOW`。

## 不可违反的规则

1. 不自动执行 `git merge`、`git push`、`git reset`、`git stash`、`git checkout`、`git worktree remove` 或分支删除。
2. 不使用 `--force` 清理 worktree 或分支。
3. 不因为分支已合并，就忽略 dirty、untracked、locked、detached 或正在进行的 Git 操作。
4. 不把 remote-tracking ref 当作实时远端状态；未执行 fetch 时必须披露可能过期。
5. 不声称检测到了真实的“会话所有者”。Git 元数据不能证明某个目录无人使用。
6. `SAFE_TO_MERGE` 或 Adapter `PASS` 只代表 Git 检查没有发现阻塞，不代表测试通过、代码正确、需求完成或已获评审批准。
7. `SAFE_CANDIDATE` 不是自动删除许可，必须有人确认实际用途和活跃进程。
8. 脚本失败或检查不可用时输出 `INVALID` 或 Adapter `UNKNOWN`，不得编造安全结论。
9. Control Adapter 不生成 `DEC`，不写入 `current_decision_refs`，不修改 Control Record。

## 可选确定性脚本

| 脚本 | 用途 | 是否修改仓库 |
|---|---|---|
| `scripts/inspect_repository.py` | 汇总仓库、分支、upstream、dirty 和 worktree 状态 | 默认不修改；`--output` 写报告 |
| `scripts/check_worktree.py` | 开始工作前检查当前 worktree | 默认不修改；`--output` 写报告 |
| `scripts/check_merge_readiness.py` | 合并前检查 ancestry、冲突、worktree 和远端跟踪状态 | 默认不修改；`--output` 写报告 |
| `scripts/check_push_readiness.py` | 推送前检查本地分支与 remote-tracking ref 的分叉 | 默认不修改；`--output` 写报告 |
| `scripts/list_cleanup_candidates.py` | 清理前列出候选、阻止项和人工建议命令 | 默认不修改；`--output` 写报告 |

## 输出要求

面向用户时，至少包含：

- Git 层面的结果；
- 阻止项和警告；
- freshness；
- 脚本没有检查或无法证明的边界；
- 下一步应由谁显式执行。

不要只说“安全”“没问题”或“可以删”。
