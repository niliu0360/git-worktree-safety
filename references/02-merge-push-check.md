# 模式二：合并或推送前检查

## 合并前检查

`check_merge_readiness.py` 检查：

- source 与 target ref 是否存在；
- source 和 target 是否相同；
- source/target 如果被某个 worktree 检出，该 worktree 是否干净；
- source/target worktree 是否存在未结束 Git 操作；
- source 是否已经包含 target；
- source 是否已经被 target 包含；
- `git merge-tree --write-tree` 是否报告冲突；
- source 与 upstream 的 ahead/behind；
- target 与 upstream 的 ahead/behind。

### 远端规则

- target 落后其 upstream：`DO_NOT_MERGE`。
- target 领先 upstream：警告，因为本地 target 含有尚未推送的提交。
- source 领先 upstream：默认警告；指定 `--require-source-pushed` 时阻止。
- source/target 没有 upstream：默认警告；指定严格参数时阻止。
- 无法计算 source/target 与 upstream 的 ahead/behind：默认警告；对应严格参数启用时阻止。

这些比较只使用本地 remote-tracking refs。脚本不执行 fetch。

### 冲突规则

若当前 Git 支持 `merge-tree --write-tree`，脚本会把生成对象隔离到系统临时目录，源仓库对象库保持不变：

- 返回 clean：通过；
- 返回 conflict：阻止合并；
- 命令不可用：降级为警告，不伪装成已经验证无冲突。

## 推送前检查

`check_push_readiness.py` 检查：

- 本地分支是否存在；
- upstream 或显式 `--remote-ref` 是否存在；
- 本地分支与 remote-tracking ref 的 ahead/behind；
- 该分支所在 worktree 是否有未结束 Git 操作；
- dirty 状态是否需要警告或阻止。

### 推送判定

- 本地落后 remote-tracking ref：`DO_NOT_PUSH`。
- ahead 为 0：`PUSH_WITH_WARNINGS`，通常表示没有新提交可推送。
- ahead > 0 且 behind = 0：在其他检查通过时为 `SAFE_TO_PUSH`。
- 无法计算 ahead/behind：`DO_NOT_PUSH`，不得把未知状态解释为安全。

本 Skill 不判断 force-push、受保护分支、服务端 hooks、PR 审批或 CI 状态。
