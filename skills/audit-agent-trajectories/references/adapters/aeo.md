# AEO AnalysisAgentAdapter

## 适用范围

AEO 模式接收平台已经裁剪、脱敏并带 evidence key 的 `AnalysisAgentAnalyzeInput`，用于
Run 的 Job 异常说明与聚合归因、单 Trial/Trace 的语义解释，以及已对齐 Trace pair 的差异归纳。它不读取
PostgreSQL、S3、Raw trajectory、Agent workspace 或完整 Artifact，也不替代离线文件审计。

文件型 Harbor/Pier job 继续使用 `scripts/audit_trajectories.py`。AEO Viewer Trace ZIP 只有
Agent 投影，不能通过改名为 `agent/trajectory.json` 冒充完整 Trial 证据。

## 输入准入

请求使用 AEO `AnalysisAgentAnalyzeInput`：

- `facts` 只包含确定性 Trial/Trace feature、outcome、环境状态、版本，以及当前布局的
  Case 行、full-population candidate cohort 和优先行动；Verifier endpoint 不能冒充 Root Cause；
- 当前客观布局的 `evidence` 最多 30 条且 Case 示例最多 20 个，先选异常和多信号失败，
  再选普通 Verifier fail 与成功对照；每条有稳定 key、类型、标签和有界摘要；旧冻结布局最多 100 条；
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

- 插件启用后，只自动分析激活时间之后新生成的 Run/Job snapshot。
- 历史 Run 由登录用户首次显式请求，后续刷新仅管理员可执行；相同 adapter、model、policy 和 input hash 幂等复用。
- 插件失败只改变 Agent AnalysisJob 状态，不影响确定性 Trial、Trace、Job 或 Verifier。
- Web 只在 Job 页面展示整体轨迹分析；Trial、Trace、Case、对比和报表不展示或触发 AI 分析。
- 人工 Root Cause 只能通过 append-only Trial revision 保存，不能由插件直接修改。

## Run scope

当前 AEO Run scope 固定请求以下九个客观维度，并要求每个维度恰好返回一个 item：

- `job_data_health_summary`：总体、Trace/feature/telemetry coverage 与缺失限制；
- `job_outcome_summary`：pass@1 与 Canonical outcome，不依赖多个正式 repeat；
- `job_verifier_summary`：Verifier 结论、覆盖和错误；
- `job_execution_health_summary`：执行终态、恢复、超时、错误域和环境候选；
- `job_latency_efficiency_summary`：总耗时、Case 分布和删失边界；
- `job_model_resource_summary`：Token、Cache、Reasoning、轮次、成本和 Case 分布；
- `job_tool_process_summary`：Tool 分类、结果、重试、workspace 与 validation 事件；
- `job_delivery_validation_summary`：Patch、capture、改动范围和验证覆盖；
- `job_risk_optimization_summary`：最值得先处理的问题与具体优化建议；
- 最多 30 条 Job/Trial/Trace evidence 和 20 个分层 Case 示例用于当前布局，旧布局上限 100；
  Case cohort 来自全量确定性事实，evidence 仍只是下钻样本；
- 不把候选计数、失败测试数或截断 evidence 写成全量根因率。

每项 detail 依次使用“## 关键结论/## 行动/## 影响范围与证据”三个二级标题：

- 关键结论通常一至两句，一句话只说一个结论，分段或分条写；不列举证据、Case 或指标明细。
  影响判断的不确定性直接写进结论，例如“缺少测试记录，暂时无法判断是否漏测”。item 标题也只写简短结论，不复述维度名。
- 行动主要用于提高得分、减少 Token、缩短耗时，或解决评测环境、作弊等问题；只选与当前问题相关的优化，
  不要求凑齐所有方向或每个维度都有建议。最多两条，每条用一句通俗的话说清具体改什么，
  不要求优先级、owner、范围、目标指标和验收清单。不要默认写成补记录、看报告或继续分析；
  必须先排查才能选择修复时，一句话说清查什么，以及据此决定怎么改。
  证据不足时写“暂无法给出优化建议。”，把缺失放到文末；确认没有待优化问题时写“无需动作。”。
- 影响范围与证据合并为文末一个短段落，概括同类问题，按需保留输入提供的受影响数/可分析数及关键限制；
  不堆砌 Case 名单或 evidence key。只有能帮助理解时才点名代表 Case，并注明它是示例。
  可追溯引用保留在结构化 `evidenceKeys` 中，不在正文重复整段证据。

优化要对应已观察到的问题：得分针对遗漏的需求或验证步骤，Token 针对不必要的重复上下文或调用，
耗时针对已知等待、重试或冗余步骤，环境针对已证实的依赖、配置或资源故障。
提高得分依靠正确完成任务，不得建议削弱 Verifier 或利用评分链；作弊只有直接证据支持时才建议封堵对应路径，
候选信号只建议针对性核查。不能仅因 Token 高或耗时长就削减推理、测试或执行额度。

当前 AEO Markdown 禁用原始 HTML，单改 skill 无法新增折叠交互，因此末段使用精简的普通 Markdown，
不输出 `<details>` 标签或假装已经折叠。九维、JSON 字段和 evidence key 契约保持不变；
2.4 的九个旧 task kind 继续保留在 profile 中，使新 Skill 可先导入旧 AEO；新 AEO 选择当前九维，
历史方案仍按冻结的旧 task kind 执行和解释。

## 完成检查

- 所有 item 都能解析为共享 contract，且只引用已提供 evidence。
- output tokens、费用、输入输出字节和来源命中 AEO 上限与 allowlist。
- 输出没有把 health、outcome、failure mode 和 root cause 混为同一结论。
- 证据不足、矛盾或不可比较时明确降级，没有补零或猜测。
