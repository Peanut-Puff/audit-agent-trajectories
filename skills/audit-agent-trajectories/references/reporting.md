# 报告与机器输出规范

## AEO Job 输出

AEO 的结构化 Job 分析使用 [AEO Adapter](adapters/aeo.md#run-scope) 的简短三段格式：关键结论、
行动、文末合并的影响范围与证据。运行时指令由该 Adapter 链接的 profile 提供。
下文的完整离线报告顺序、逐 Trial 模板和聚合明细不应套用到 AEO 每项 detail。

## Compact 输出

```text
<output>/
|-- audit.json
|-- findings.jsonl
`-- report.md
```

Skill 默认调用 `--output-layout compact`。`audit.json` 是确定性、可重建层，包含 manifest、trials、comparability、comparison stats、candidates 和 selection；`findings.jsonl` 与 `report.md` 属于人工产物，提取器只在不存在时创建，不得覆盖。

显式 `--html` 可附加可重建的 `report.html`，也可独立渲染已有审计。支持单 Trial/配对 Trial 与单 Job/双 Job 总览，Job 另附 `report-details/` 静态详情目录；语义阶段、请求曲线、筛选统计和证据下钻见 [HTML 展示层](html-presentation.md)。默认三文件 compact 契约不变，AEO runtime 仍返回 JSON。

## Expanded 兼容布局

CLI 默认仍为 `expanded`，供依赖旧文件路径的自动化显式使用：

```text
<output>/
|-- generated/
|   |-- manifest.json
|   |-- trials.jsonl
|   |-- trials.csv
|   |-- comparability.csv
|   |-- comparison-stats.json
|   |-- candidates.jsonl
|   `-- selection.csv
|-- adjudicated/
|   `-- findings.jsonl
`-- report.md
```

## Manifest

至少记录 `methodology_version`、schema/script/rule version、生成时间、mode、depth、focus、输入绝对路径与 hash、输出路径、trial 数、adapter 计数、selection 规则、bootstrap seed/次数、脱敏策略和限制。

## Trial 记录

每行至少包含：

- job/trial/task identity、checksum、baseline、prompt/verifier/patch fingerprint；
- adapter、model、agent/runtime、environment type；
- overall health 和逐维度 coverage；
- raw/reconciled reward、F2P/P2P/N2P/S2P；
- duration、censoring、可证 phase duration；
- input/output/cache read/cache creation/cost 和 ledger 来源；
- step/tool/mutation/validation 计数和最终 mutation 后验证；
- patch path/hash/stats、关键 artifact path/hash；
- provenance、缺失、矛盾和限制。

Compact 布局在 `audit.json.trials` 保留完整记录。Expanded 布局的 CSV 是便于筛选的扁平子集，完整嵌套证据保留 JSONL；两者数据行数必须等于枚举 trial 数。

## Candidate 与 Finding

Candidate 至少包含：`methodology_version`、`rule_version`、`trial_key`、`focus`、`candidate_type`、`status=heuristic`、`step_id`、`evidence_paths`、脱敏摘要和规则细节。

Finding 至少包含 candidate 引用、`adjudication=confirmed|rejected|indeterminate`、专项状态、直接证据、替代解释、置信度、分析者和时间。环境责任、评测违规、FMEA 和根因使用各自 taxonomy，不共用含糊 `label`。

## 中文主报告顺序

1. 范围、方法版本、job 身份、manifest、raw/reconciled truth。
2. 一页结论，分开 full measurement、sample mechanism 和 hypothesis。
3. 健康与逐维度 coverage。
4. 可比性、配对总体、缺失和统计口径。
5. 得分与 verifier。
6. 用户关注的环境、完整性、Token、耗时、交付链专项结果。
7. FMEA 和深读归因；标准模式明确禁止外推，完整模式才给全量根因分布。
8. Strict cohort、主题聚类、控制、验收指标和证据限制。

正文表格通常不超过 5 列；完整英文键、长文本和逐 trial 记录留在 JSONL/CSV。技术标识符保留原文，叙述使用中文。

## 单 Trial 深读模板

默认采用[人工语义时序报告](audits/semantic-trial-analysis.md)：任务内目标/方案/返修细分，单 Trial 按时间展示，一对 Trial 先各自时序再同目标对齐；不以 E/B/I/V/P 替代人工深读。下面的失败证据链作为报告的必要内容，按任务需要放入正文或证据抽屉。整个 Job 阶段概览首选 E/B/I/V/P。

```markdown
# <task> / <job>

- Trial / Viewer / checksum / model-runtime
- Health 与逐维度 coverage
- Raw/reconciled reward；F2P/P2P/N2P/S2P

## 任务契约
- 目标：<一句中文>
- 契约矩阵：<行为、边界、错误、优先级、兼容、验收>

## Verifier 解释
- 每个失败：输入/状态、期望、实际、代码路径、证据边界

## 首个可证实现
- Step、文件、符号、3-20 行原始关键代码
- 代码如何产生 verifier 实际结果

## 为什么这样写
- 最早转述、错误规则、直接理由或动机不可证、形成路径

## 根因复核
- 唯一主分类、机制键、首错四条件
- 最强替代分类、反证、反事实
- 失败机制/代码成因/最终归因置信度

## 结束检查
- 任务条目 -> 实现位置 -> 定向断言 -> 观察结果
- Secondary factors、成功对照、cohort 资格和证据限制
```

通过 trial 不定位主失败，只报告独立 verifier 通过证据。`infra_failed` 且无可评价 patch 时报告故障点、证据和重跑条件，不强行写行为根因。

## 聚合报告要求

- 每个数字标明层级、单位、分子、分母、缺失、比较资格和方法。
- 每个失败 trial 在机器索引中保留 health、integrity、score、主因/无法归因理由、首错 step、置信度和证据路径。
- Candidate 和 adjudicated finding 分表；严格 cohort 和主题聚类分开。
- 标准模式不得出现全量机制发生率；完整模式保留无法归因项。

## 语言纪律

使用“观察到”“与……一致”“无法区分”“证据不足以支持”。除非证据闭环，不写“模型不会推理”“OOM”“浪费 token”“根因已证明”。测试源码不可见时，示例必须标为等价示意。

## 交付检查

- Markdown 相对链接可解析，所有 reference 可从方法索引或入口到达。
- Compact 的 `audit.json` 各数组或 expanded 的 Trial JSONL/CSV、comparability 和 selection 行数与范围一致。
- 缺失没有变成 0，敏感值没有进入生成物。
- 重跑不改变人工文件。
- 报告清楚区分健康、结果、failure mode 和 root cause。
- 配对统计给出等级、有效/缺失 n、seed 和不确定性。
- 所有重要结论可下钻到绝对路径、step、hash 或 verifier assertion。
