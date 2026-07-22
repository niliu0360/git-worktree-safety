# git-worktree-safety 0.1.0

一个面向 AI Coding、多窗口和多 Agent 并行开发的 Git / worktree 安全检查 Skill。

它回答：

- 当前 worktree 是否适合继续修改；
- 源分支是否具备合并到目标分支的 Git 条件；
- 本地分支是否适合推送到已有 upstream；
- 哪些旧 worktree 只是“Git 层面候选”，哪些必须保留或人工复核。

## 为什么单独做成 Skill

`completion-discipline` 判断“需求是否完成”。

`git-worktree-safety` 判断“当前 Git 操作是否安全”。

两者边界不同：代码可以安全合并，但需求仍可能遗漏；需求已经完成，也可能因为脏 worktree、远端落后或冲突而不能合并。

## 0.1.0 的安全边界

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
- 仅使用 Python 标准库

## 快速开始

### 1. 检查当前仓库

```bash
python /path/to/git-worktree-safety/scripts/inspect_repository.py --repo .
```

### 2. 开始修改前

```bash
python /path/to/git-worktree-safety/scripts/check_worktree.py --repo .
```

### 3. 合并前

```bash
python /path/to/git-worktree-safety/scripts/check_merge_readiness.py \
  --repo . --source feature/example --target main
```

### 4. 推送前

```bash
python /path/to/git-worktree-safety/scripts/check_push_readiness.py \
  --repo . --branch main
```

### 5. 清理 worktree 前

```bash
python /path/to/git-worktree-safety/scripts/list_cleanup_candidates.py \
  --repo . --merged-into main --idle-days 7
```

所有脚本默认把 JSON 输出到 stdout。使用 `--output report.json` 可同时写入文件。

## 退出码

| 退出码 | 含义 |
|---:|---|
| `0` | 安全结论或成功完成只读审计 |
| `1` | 存在警告，需要披露或人工复核 |
| `2` | 存在阻止项、无效输入或无法安全判断 |

`list_cleanup_candidates.py` 是批量审计工具，只要审计成功就返回 `0`；应读取每个 worktree 的独立 verdict。

## 远端状态说明

脚本不会自动执行 `git fetch`。因此：

- `origin/main` 可能已经过期；
- “target 未落后远端”只表示未落后本地已有的 remote-tracking ref；
- 对合并或推送做最终判断前，应由用户显式运行 `git fetch --prune`，再重新检查。

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

因此 0.1.0 不实现自动 worktree 所有权和自动清理。

## 测试

```bash
bash tests/run_all.sh
```

测试使用临时 Git 仓库和 worktree，不访问网络，也不修改真实项目。

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
├── schemas/
├── examples/
└── tests/
```
