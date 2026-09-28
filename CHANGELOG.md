# Changelog

本项目遵循 Semantic Versioning。日期使用 `YYYY-MM-DD`。

## [2.0.0] - 2026-09-28

### Added

- 将轨迹审计方法拆为统一生命周期、证据准入、可比性、八类专项审计、聚合、adapter 和报告规范。
- 提供标准库 Python 确定性提取器、12 个合成测试和真实 Harbor 产物适配。
- 提供 `npx skills`、Codex、Claude Code、BitFun 和通用 Agent Skills 安装说明。
- 增加仓库级版本、包校验和 CI。

### Compatibility

- CLI 保持 `audit_trajectories.py INPUT... --output DIR [--mode] [--depth] [--focus]`。
- 方法版本为 `2.0.0`，提取规则为 `trajectory-audit-v2`，机器 schema 为 `1`。
