# git-worktree-safety 0.1.0

> **Status: Public Beta** — explicit workflow, deterministic checks, no automatic enforcement.

Conservative Git and worktree safety checks for parallel AI coding workflows.

一个面向 AI Coding、多窗口和多 Agent 并行开发的 Git / worktree 安全检查 Skill。

它回答：

- 当前 worktree 是否适合继续修改；
- 源分支是否具备合并到目标分支的 Git 条件；
- 本地分支是否适合推送到已有 upstream；
- 哪些旧 worktree 只是“Git 层面候选”，哪些必须保留或人工复核。

## 为什么单独做成 Skill

`completion-discipline` 判断“需求是否完成”。

`ai-engineering-control-layer` 决定某个动作当前是 `ALLOW`、附条件允许、需要人工批准还是 `BLOCK`。

`git-worktree-safety` 只提供 Git/worktree 事实。它不决定需求是否完成，也不独立授权合并、推送、发布或删除。

## 0.1.0 首发能力

五个脚本都支持两种输出：

```text
--format legacy           # 默认，兼容原有 JSON
--format control-adapter  # AICR 0.2 Adapter Result
```

Control Adapter 固定使用：

```text
scope = GIT_STATE_ONLY
result = PASS | WARN | BLOCK | UNKNOWN
```

它还包含：

- `observed_at` 和唯一 run ID；
- repository、worktree、branch、source/target ref 和 head OID 快照；
- `checks`、`blocking_items`、`warnings`、`limitations`；
- 未自动 fetch 的 freshness 声明；
- 可投影到 Evidence Ledger 的 `git_state` 状态；
- 原有 `legacy_verdict`，便于渐进迁移。

例如：

```bash
python scripts/check_merge_readiness.py \
  --repo . \
  --source feature/payment \
  --target main \
  --format control-adapter \
  --output .ai-control/adapters/git-merge.json
```

生成结果可由 Control Layer 导入，但 **Control Layer 仍需结合 Acceptance Contract、Risk、Evidence 和人工审批重新作出 Policy Decision**。

## 安全边界

本版本刻意只做检查。它不会：

- 注册 Claude Code hooks；
- 拦截 Bash 命令；
- 创建全局会话锁；
- 自动执行 `git fetch`；
- 自动 merge、push、reset、stash 或 checkout；
- 自动删除 worktree 或分支；
- 根据 PID、目录时间或推测认定某个 AI 会话已经结束。

## 安装

将整个 `git-worktree-safety` 目录复制到 AI Coding 工具支持的 Skills 目录，或直接让工具读取 `SKILL.md`。

脚本要求：

- Python 3.9+
- Git 2.38+ 建议版本；合并检查把 `merge-tree --write-tree` 产生的临时对象隔离到系统临时目录，不写入目标仓库对象库；较旧 Git 会降级为警告
- 运行时仅使用 Python 标准库

支持情况：

- Linux：通过 GitHub Actions 测试；
- macOS：脚本仅依赖 Python 标准库和 Git，预期兼容，尚未纳入 CI；
- Windows WSL2：已人工验证；
- Windows 原生：尚未验证。

## 快速开始

### 检查当前仓库

```bash
python scripts/inspect_repository.py --repo .
```

### 开始修改前

```bash
python scripts/check_worktree.py --repo .
```

### 合并前

```bash
python scripts/check_merge_readiness.py \
  --repo . --source feature/example --target main
```

### 推送前

```bash
python scripts/check_push_readiness.py \
  --repo . --branch main
```

### 清理 worktree 前

```bash
python scripts/list_cleanup_candidates.py \
  --repo . --merged-into main --idle-days 7
```

所有脚本默认把 JSON 输出到 stdout，不修改 Git refs、index、配置或已有文件。使用 `--output report.json` 时会创建或覆盖用户指定的报告文件；若路径位于仓库内，工作区可能因此变脏。

## 退出码

| 退出码 | 含义 |
|---:|---|
| `0` | 安全结论或成功完成只读审计 |
| `1` | 存在警告，需要披露或人工复核 |
| `2` | 存在阻止项、无效输入或无法安全判断 |

切换到 `control-adapter` 只改变 JSON 结构，不改变原检查的退出码。

`list_cleanup_candidates.py` 是批量审计工具，只要审计成功就返回 `0`；应读取每个 candidate check 的状态。混合候选的 Adapter 总结果为 `WARN`，不会把某个安全候选自动变成删除许可。

## 远端状态说明

脚本不会自动执行 `git fetch`。因此：

- remote-tracking refs 可能已经过期；
- “target 未落后远端”只表示未落后本地已有的 remote-tracking ref；
- 对合并或推送做最终判断前，应由用户显式运行 `git fetch --prune`，再重新检查；
- Control Adapter 会明确输出 `fetch_performed: false` 和 `remote_state_may_be_stale: true`；
- 如果现有 refs 无法计算 ahead/behind，推送检查会阻止，合并检查会警告；启用相应严格参数时合并检查也会阻止。

## 会话所有权说明

Git 自身没有“Claude 会话拥有这个 worktree”的标准字段。

本 Skill 可以发现：

- 分支与 worktree 的对应关系；
- worktree 是否 locked；
- dirty、untracked 和进行中的 Git 操作；
- 分支是否已合入目标分支。

但不能证明：

- 没有其他编辑器或后台进程正在使用目录；
- 某个 AI 会话已经退出；
- 最近未修改的目录一定无人使用。

因此不会实现自动 worktree 所有权和自动清理。

## 测试

```bash
python -m pip install jsonschema  # 仅测试 Schema 时需要
bash tests/run_all.sh
```

测试使用临时 Git 仓库和 worktree，不访问网络，也不修改真实项目。CI 覆盖 Python 3.9–3.13，并同时验证旧格式兼容和 AICR Adapter Result Schema。

## 文件结构

```text
git-worktree-safety/
├── SKILL.md
├── README.md
├── VERSION
├── CHANGELOG.md
├── LICENSE
├── references/
├── scripts/
│   └── _control_adapter.py
├── schemas/
│   └── adapter-result.schema.json
├── examples/
└── tests/
```
