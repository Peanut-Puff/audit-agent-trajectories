# AEO AnalysisAgentAdapter

## 适用范围

AEO 模式接收平台已经裁剪、脱敏并带 evidence key 的 `AnalysisAgentAnalyzeInput`，用于
Run 的 Job 异常说明与聚合归因、单 Trial/Trace 的语义解释，以及已对齐 Trace pair 的差异归纳。它不读取
PostgreSQL、S3、Raw trajectory、Agent workspace 或完整 Artifact，也不替代离线文件审计。

文件型 Harbor/Pier job 继续使用 `scripts/audit_trajectories.py`。AEO Viewer Trace ZIP 只有
Agent 投影，不能通过改名为 `agent/trajectory.json` 冒充完整 Trial 证据。

## 输入准入

请求使用 AEO `AnalysisAgentAnalyzeInput`：

- `facts` 只包含确定性 Trial/Trace feature、outcome、环境状态、版本和已有 Root Cause；
- `evidence` 最多 100 条，每条有稳定 key、类型、标签和有界摘要；
- `taskTypes` 限制本次允许返回的分析类型；
- `model`、`policyVersion`、Token 和费用上限由 AEO 后台冻结；
- 输入已经脱敏，但仍不得在输出中复制不必要的长命令、日志或疑似凭据。

先检查 facts 中的 feature status、缺失和矛盾，再决定结论强度。只有 verifier 摘要而没有
任务契约、关键 patch 或 reasoning/tool evidence 时，根因保持 indeterminate。`infra_failed`
且没有可评价 patch 时只解释故障和重跑条件，不写行为根因。

## Runtime profile

AEO 宿主不得复制方法论 prompt。仓库使用
[`aeo-runtime-prompt.md`](./aeo-runtime-prompt.md) 作为权威运行时指令，并通过
`scripts/build_aeo_profile.py` 生成 `runtime/aeo-profile.json`。profile 固定：

- `schemaVersion=aeo-analysis-methodology-profile/1.0`；
- `externalAgent=audit-agent-trajectories`；
- `methodologyVersion`，与仓库 `VERSION` 一致；
- `requestSchemaVersion=aeo-audit-agent-input/1.0`；
- `responseLanguage=zh-CN`；
- 支持的 task type 与完整 system prompt。

宿主启动时必须校验 profile SHA-256，并把 profile 版本纳入 adapter 版本或 input hash。
本地开发可以直接读取当前 skill 目录中的 profile；部署环境必须复制同一不可变字节，不能依赖
开发机绝对路径或可变 `latest`。

## 请求与响应

Profile 不规定 HTTP、OpenAI、ACP 或 native SDK transport。AEO 内置插件当前使用
OpenAI-compatible Chat Completions：system message 来自 profile，user message 携带版本化
`AnalysisAgentAnalyzeInput`、methodology version 和响应 schema。宿主从 provider envelope 中
提取 JSON，再校验为 AEO `AnalysisAgentAnalyzeResult`。每个 item 必须：

- `kind` 属于请求的 `taskTypes`；
- `evidenceKeys` 只引用请求中存在的 key；
- `hypothesis` 固定为 `true`；
- `externalAgent`、`model` 与 AEO allowlist 一致；
- `title/detail` 使用简体中文；
- 使用“观察到”“与……一致”“无法区分”，不把 candidate 升级为 finding。

HTTP endpoint 默认使用 HTTPS；loopback 开发 endpoint 可直接使用 HTTP，任何环境的 non-loopback
HTTP 都必须由宿主通过 Analysis Agent 专用开关显式开启。生产仅允许受控私网 endpoint，并必须
通过私网路由和安全组限制访问；HTTP 会明文传输 API key 和分析数据。API key 只进入
Authorization header，不得进入 profile、prompt、请求 JSON、普通日志或 AnalysisResult。

## AEO 生命周期

- 插件启用后，自动分析激活时间之后新生成的 Job snapshot，以及带 Trace 且 outcome 为 `failed` 的 Trial feature；通过和其他非失败 Trial 只在管理员显式请求后分析。
- 历史 Run/Trial 由管理员显式请求；相同 adapter、model、policy 和 input hash 幂等复用。
- 插件失败只改变 Agent AnalysisJob 状态，不影响确定性 Trial、Trace、Job 或 Verifier。
- Web 在 Job 页面展示“整体审计”，在 Trace Viewer 展示“轨迹审计”；item 均标记为 Agent 推测，并保留 adapter、模型、policy、input hash 和 evidence。Trial 页面不重复展示。
- 人工 Root Cause 只能通过 append-only Trial revision 保存，不能由插件直接修改。

## Run scope

Run scope 固定请求以下九个维度，并要求每个维度恰好返回一个 item：

- `job_health_summary`：健康与逐维度 coverage；
- `job_score_summary`：Canonical outcome、可靠性和 Verifier 事实；
- `job_environment_summary`：环境事件、Agent 恢复行为和责任边界；
- `job_integrity_summary`：实际外联/评分链证据与候选信号的区分，不把无候选写成合规证明；
- `job_token_cost_summary`：Token 账本、Cache 口径、成本值与缺失覆盖；
- `job_latency_summary`：完成/删失样本、ATIF/typed timing 与缺失覆盖；
- `job_delivery_summary`：Patch、capture、validation 和交付覆盖；
- `job_anomaly_summary`：只读取不可变 Job snapshot 的全量跨维度异常；
- `job_attribution_summary`：只汇总当前 effective Attempt 的全量已有确定性 Trial Root Cause，并明确已归因、未归因和分母；
- 最多 100 条 Job/Trial/Trace evidence 用于下钻示例，不得把这批 evidence 当作全量机制样本；
- 不把候选计数、失败测试数或截断 evidence 写成全量根因率。

## 完成检查

- 所有 item 都能解析为共享 contract，且只引用已提供 evidence。
- output tokens、费用、输入输出字节和来源命中 AEO 上限与 allowlist。
- 输出没有把 health、outcome、failure mode 和 root cause 混为同一结论。
- 证据不足、矛盾或不可比较时明确降级，没有补零或猜测。
