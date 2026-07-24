# Changelog

## 0.2.0-beta.1 — 2026-07-24

- 为五个只读检查脚本增加 `--format control-adapter`。
- 新格式遵循 AICR 0.2 Adapter Result：`PASS / WARN / BLOCK / UNKNOWN`。
- 固定输出边界 `scope: GIT_STATE_ONLY`，不再让 Git 结论看起来像整体合并、推送或发布授权。
- 增加 `observed_at`、run ID、仓库/分支/ref 快照、freshness、limitations 和 suggested actions。
- 保留原有 0.1 JSON 为默认输出，现有调用方无需立即迁移。
- 批量清理审计保留每个 worktree 的候选级 PASS/WARN/BLOCK，不把混合候选误解释为全局删除授权。
- 增加与 Control Layer 相同的 Adapter Result JSON Schema 和 Python 3.9–3.13 验证。

## 0.1.0 — 2026-07-22

首个公开 Skill 版本。

- 单一 `git-worktree-safety` 主 Skill，包含三个模式：开始工作前检查、合并/推送前检查、清理前审计。
- 提供四个只读确定性脚本：仓库检查、当前 worktree 检查、合并就绪检查、清理候选审计。
- 所有危险操作默认不执行：不 merge、不 push、不 reset、不 stash、不删除 worktree 或分支。
- `git fetch` 不由脚本自动执行；远端同步判断只基于本地已有的 remote-tracking refs。
- 明确区分 Git 安全与需求完成：本 Skill 不替代测试、代码评审或 completion-discipline。
- 增加 JSON Schema、示例、自动化测试和 MIT License。
- ahead/behind 无法计算时改为保守警告或阻止，不再产生虚假的安全结论。
- 明确 `--output` 会写入用户指定的报告文件。
- 增加 Python 3.9–3.13 CI、Public Beta 状态和公共贡献/安全说明。
