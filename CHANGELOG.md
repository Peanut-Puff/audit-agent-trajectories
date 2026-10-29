# Changelog

本项目遵循 Semantic Versioning。日期使用 `YYYY-MM-DD`。

## [2.8.0] - 2026-10-29

### Added

- 新增标准库 HTML 展示器和显式 `--html` 附加输出，支持单 Trial、配对 Trial、单 Job 和双 Job 总览，兼容 compact/expanded 审计。
- Job 总览增加结果分布、逐指标分母、覆盖矩阵、同步筛选、分页任务列表和预生成静态详情；批量配对按任务聚类重采样，未知结果与各指标排除项独立保留。
- 增加浅灰/白底、蓝色与陶土橙对照的离线页面，包含请求输入/累计输入曲线、健康覆盖、raw/reconciled verifier、交付链、候选与裁决的统一证据下钻。
- 增加可选 `trial-presentation/1` 人工语义阶段和请求时间标注；自动 E/B/I/V/P 另行展开，缺失输入、未归属请求和账本差额独立保留。
- 语义阶段按轮次、耗时、token 展示共用刻度的对照横条；说明按需展开。证据改为中文说明卡，原始字段和路径默认收起，保留已有锚点直达。
- Trial 曲线改为单图下拉切换，保留累计输入、单次输入、累计输出、累计 Reasoning 和累计未缓存输入五项；缺失数据与缓存包含关系分别处理，沿用蓝橙主题。
- 增加 HTML 的合成回归检查与 CI；覆盖深度隔离、配对准入、缺失值、标注重叠、脱敏、脚本注入及人工文件保护。

### Compatibility

- 默认 compact 三文件契约、既有 CLI 默认、机器 schema 与候选/adapter 规则不变；HTML 可重建，人工 findings 和 `report.md` 不覆盖。
- AEO 响应仍为 JSON，prompt 语义不变，仅同步方法版本；HTML Job 详情使用相邻静态目录，首页不嵌入全部请求轨迹。

## [2.7.0] - 2026-10-27

### Added

- 新增标准库事件归一化器，统一处理 Harbor 目录、AEO case-log 目录和原始 case-log ZIP，输出最小 model-round/tool-call 账本。
- 新增相互独立的轮次动作分类器和 E/B/I/V/P stage 投影器；默认只输出紧凑汇总，逐轮结果按需开启。
- 增加 BitFun request trace、OpenCode event log、ZIP 直读、subagent、混合编辑验证、baseline 阶段和 stable-green 边界的合成回归测试。

### Changed

- 通用脚本只承担格式归一化、动作分类和阶段投影，不固化 Review、返修循环、得分视图或特定 job 报表。
- 失败审计明确区分 failure surface、responsibility candidate 和 root cause。
- Skill 默认使用三文件 compact 审计交付；旧 generated/adjudicated 多文件结构保留为显式 expanded 兼容模式。
- 轮次归一化压缩为 summary 加单一事件包，动作与 stage 默认各输出一个 JSON。
- 轮次动作分类对齐 BitFun `analyze-agent-case-logs.py`：使用相同完成轮次、工具/命令识别、结构化 validation telemetry 和 `verification > editing > exploration > other` 优先级。
- Token coverage 对齐 BitFun 诊断脚本：聚合 `step_results`、拒绝无完成请求证据的零填充值，并用 `aeo_model_usage` 判定 complete/partial/missing。
- README 和安装指南只保留以 `Peanut-Puff/audit-agent-trajectories` 为 source 的 `npx skills` 安装与更新方式。

### Fixed

- 嵌套 `agent.zip` 使用 Python 3.10 兼容的临时文件接口，修复 `SpooledTemporaryFile` 缺少 `seekable` 导致的 CI 失败。

## [2.6.0] - 2026-10-19

### Added

- AEO Run 报告使用确定性 Case 行、失败 cohort、分层样本和成功对照生成可定位结论。
- 优化建议固定优先级、owner、精确影响范围、目标指标和验证方法。

### Changed

- 九维 detail 改为关键结论、影响范围、行动和证据边界，不再复述页面已有指标。
- 禁止没有具体 Case/诊断问题的泛化“复查、重跑、比较 P90”建议；证据不足时明确无需动作或分析阻塞。
- Verifier fail、候选信号和根因保持分层，缺失 delivery 遥测不再解释为 Agent 没有 Patch。

## [2.5.0] - 2026-10-15

### Added

- AEO Run scope 增加数据健康、结果、Verifier、执行健康、耗时效率、模型资源、Tool 过程、交付验证、风险优化九个客观维度。
- 每个新维度在确定性统计之上提供受证据约束的分析解释、证据限制和可验收优化建议。

### Changed

- 单次评测默认布局移除依赖多个正式 repeat 的稳定性维度；旧九维 task kind 保留兼容。
- Dataset 或 Binding 不支持某类遥测时保持 `unsupported|partial|absent`，不省略维度或补零。
- 当前客观布局把模型输入限制为 30 条 evidence 和 20 个 Trial 示例；旧冻结布局保留原上限。

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
