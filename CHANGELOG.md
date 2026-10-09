# Changelog

本项目遵循 Semantic Versioning。日期使用 `YYYY-MM-DD`。

## [2.4.0] - 2026-10-09

### Added

- AEO Run scope 增加健康与覆盖、得分与 Verifier、环境、评测完整性、Token 与成本、耗时、交付链等独立任务类型。
- Run scope 要求每个请求维度恰好返回一个中文结果；证据不足时保留缺失与覆盖率，不静默省略审计维度。

### Changed

- AEO runtime prompt 明确区分完整性候选与已裁决违规，并要求 Token、成本和耗时遵守各自口径与分母纪律。

## [2.3.0] - 2026-10-08

### Added

- 增加由 skill 权威 prompt 构建的确定性 `aeo-analysis-methodology-profile/1.0` runtime profile，包含方法版本、输入 schema、任务类型和中文输出约束。
- 增加 profile 漂移校验，使 AEO 可以按版本与 SHA-256 直接加载方法产物，而不复制方法论 prompt。

### Changed

- AEO adapter 文档改为 transport-neutral 方法 profile；HTTP/OpenAI transport 继续由宿主插件负责。

## [2.2.0] - 2026-09-29

### Added

- AEO adapter 增加 Run scope，用于 Job 异常说明和基于全量确定性投影的聚合归因。
- AEO 产品入口调整为 Job 整体审计与 Trace 轨迹审计；Trial API 仅作为 Trace 兼容数据源。

### Compatibility

- Harbor/Pier 文件提取 CLI、`trajectory-audit-v2` 规则和机器 schema `1` 保持不变。
- AEO 请求 schema 继续使用 `aeo-audit-agent-request/1.0`。

## [2.1.0] - 2026-09-28

### Added

- 增加 AEO `AnalysisAgentAdapter` 结构化 facts/evidence 输入与 hypothesis 输出规范。
- 明确 AEO 自动分析、人工重分析、证据引用、状态展示和权威结果隔离边界。

### Compatibility

- Harbor/Pier 文件提取 CLI、`trajectory-audit-v2` 规则和机器 schema `1` 保持不变。
- AEO 集成使用 `aeo-audit-agent-request/1.0`，方法版本提升为 `2.1.0`。

## [2.0.0] - 2026-09-28

### Added

- 将轨迹审计方法拆为统一生命周期、证据准入、可比性、八类专项审计、聚合、adapter 和报告规范。
- 提供标准库 Python 确定性提取器、12 个合成测试和真实 Harbor 产物适配。
- 提供 `npx skills`、Codex、Claude Code、BitFun 和通用 Agent Skills 安装说明。
- 增加仓库级版本、包校验和 CI。

### Compatibility

- CLI 保持 `audit_trajectories.py INPUT... --output DIR [--mode] [--depth] [--focus]`。
- 方法版本为 `2.0.0`，提取规则为 `trajectory-audit-v2`，机器 schema 为 `1`。
