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

当前 AEO Run scope 固定请求四个优化维度，每个维度恰好返回一个 item：

| Task kind | 页面维度 | 应回答的问题 |
| --- | --- | --- |
| `job_score_optimization` | 得分 | Agent 哪类可复用的能力或流程问题阻止更多任务通过，怎么改 Agent |
| `job_token_optimization` | Token | Agent 的提示词、上下文、工具或输出策略怎么减少重复消耗 |
| `job_latency_optimization` | 耗时 | Agent 的提示词、工具或执行策略怎么减少重复等待 |
| `job_other_optimization` | 其他（环境、作弊等） | 有什么环境、依赖、资源或完整性问题，怎么处理 |

当前输入保留全量确定性分母、Case cohort 和最多 20 个 Case 示例，最多 100 条 evidence。
`caseDiagnostics` 按维度优先级遍历全部可选 Case：得分按 F2P/P2P 未通过数降序，Token 按总 Token 降序，
耗时按执行时长降序，其他按环境/完整性信号排序；同一 Case 在多个维度只读取一次，成功 Case 只作少量对照。
最终受 evidence 字节和读取预算约束，不按固定 Case 数截断失败任务。每条来源经过有界读取、大小/hash 校验和脱敏，
缺失、不可读、超限、身份不一致及片段状态分别保留；失败断言定位只是选取证据，不是根因规则。
旧客观九维继续使用最多 30 条 evidence；2.4 旧布局最多 100 条。

先读诊断证据再写建议。不能用“失败全部来自校验拒绝”“无异常执行”充当得分洞见，
也不能用“补齐未通过的实现”“提高通过率”“先取得每个被拒任务的失败明细”充当行动。
不必等全量失败明细齐全才分析已有示例；过程证据也可能独立支持改进，但不得声称能挽回多少未读任务。
只有计数时，直接写“当前输入只有结果统计，无法定位具体提分改动。”，不铺陈已知结果。
数据限制只说明本次输入的边界：未传入不等于未采集，结论覆盖完整不等于失败断言完整。
Token、耗时和其他维度各自按证据分析，不因得分证据不足全部停摆。

报告面向被评测 Agent 的研发者。得分、Token、耗时的行动是改进 Agent 自身的代码、提示词、
工具、上下文管理或通用执行流程，不能给正在解题的 Agent 下达某个 Case 的修复指令。
Case 诊断用于发现可推广的机制；单个样本只能支持有边界的优化假设，不能冒充普遍规律。
任务要求、Dataset、Verifier 口径、模型和评测预算保持固定；不能建议修改这些条件来提分或降低消耗。
环境与完整性问题可以建议调整相应平台控制。

每项 detail 依次使用“## 关键结论/## 行动/## 影响范围与证据”三个二级标题：

- 关键结论通常一至两句，一句话只说一个结论，分段或分条写；不列举证据、Case 或指标明细。
  影响判断的不确定性直接写进结论，例如“缺少测试记录，暂时无法判断是否漏测”。item 标题也只写简短结论，不复述维度名。
- 行动主要用于提高得分、减少 Token、缩短耗时，或解决评测环境、作弊等问题；前三类行动面向 Agent 的通用提示词、工具、上下文或代码能力。
  不要求凑齐所有方向或每个维度都有建议。最多两条，每条用一句通俗的话说清具体改什么，
  不要求优先级、owner、范围、目标指标和验收清单。不要默认写成补记录、看报告或继续分析；
  必须先排查才能选择修复时，一句话说清查什么，以及据此决定怎么改。
  证据不足时写“暂无法给出优化建议。”，把缺失放到文末；确认没有待优化问题时写“无需动作。”。
- 影响范围与证据合并为文末一个短段落，概括同类问题，按需保留输入提供的受影响数/可分析数及关键限制；
  不堆砌 Case 名单或 evidence key，单个任务的解题文件、函数与测试留在下钻证据中；
  改进方案可以明确 Agent 自身的模块、工具或提示词组件，避免空泛。
  可追溯引用保留在结构化 `evidenceKeys` 中，不在正文重复整段证据。

优化要对应已观察到的问题：得分针对 Agent 的需求理解、实现或完成检查机制，Token 针对不必要的重复上下文或调用，
耗时针对已知等待、重试或冗余步骤，环境针对已证实的依赖、配置或资源故障。
提高得分依靠正确完成任务，不得建议削弱 Verifier 或利用评分链；作弊只有直接证据支持时才建议封堵对应路径，
候选信号只建议针对性核查。不能仅因 Token 高或耗时长就削减推理、测试或执行额度。

detail 的末段只使用普通 Markdown，由 AEO 把“影响范围与证据”与证据入口合并折叠；
skill 不输出原始 HTML。旧宿主仍可平铺显示末段。
四维 task kind 新增而不删除两个旧九维集合；新 AEO 优先选择四维，旧方案仍按冻结 task kinds 执行。
旧 AEO 可继续从同一 profile 选择其支持的九维，不改变历史结果。

## 完成检查

- 所有 item 都能解析为共享 contract，且只引用已提供 evidence。
- output tokens、费用、输入输出字节和来源命中 AEO 上限与 allowlist。
- 输出没有把 health、outcome、failure mode 和 root cause 混为同一结论。
- 证据不足、矛盾或不可比较时明确降级，没有补零或猜测。
