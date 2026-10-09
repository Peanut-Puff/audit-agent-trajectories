# 轨迹审计方法索引

方法版本：`2.4.0`。

## 方法模型

轨迹审计按五层证据推进：原始事实、派生指标、启发式候选、人工裁决、因果假设。分析顺序固定为：先判断数据能否支持问题，再判断样本能否比较，最后才进入专项分析和聚合。

四类结论必须分开：

| 结论 | 回答的问题 | 规范来源 |
| --- | --- | --- |
| 健康与覆盖 | 证据是否足以回答当前问题 | [证据与可分析性](core/evidence-and-readiness.md) |
| 任务结果 | verifier 观察到了什么 | [得分与 verifier](audits/score-and-verifier.md) |
| 失败模式 | evaluator 可观察到哪类失效 | [失败模式](audits/failure-modes.md) |
| 根因 | 最早哪个可控决策造成了结果 | [根因](audits/root-cause.md) |

## 统一生命周期

任何审计都遵循 [审计生命周期](core/audit-lifecycle.md)：范围确认、证据清点、归一化、可分析性、可比性、专项审计、深读裁决、聚合、报告 QA。阶段可以因证据不足提前停止，但不得跳过准入阶段后直接给出原因。

## 问题路由

| 用户问题 | 必读文档 | 条件文档 |
| --- | --- | --- |
| 单 trial 为什么失败 | readiness、score、delivery、failure-modes、root-cause | environment、integrity |
| 单 job 健康与质量 | readiness、failure-modes、aggregation | 各专项文档 |
| 环境稳定性 | readiness、environment、aggregation | latency、delivery |
| 作弊或评测违规 | readiness、evaluation-integrity | delivery、adapter |
| Token/成本效率 | readiness、token-and-cost、aggregation | comparability、score |
| 耗时效率 | readiness、latency、aggregation | environment、comparability |
| 得分和回归 | readiness、score-and-verifier、aggregation | root-cause |
| 跨 agent/model 配对 | readiness、comparability、aggregation | 被比较指标对应的专项文档 |
| 全量根因分布 | readiness、score、delivery、failure-modes、root-cause、aggregation | comparability |

以上表中的 `readiness` 指 [证据与可分析性](core/evidence-and-readiness.md)，`comparability` 指 [可比性与抽样](core/comparability-and-sampling.md)。

## 专项文档

- [环境与基础设施](audits/environment.md)
- [评测完整性](audits/evaluation-integrity.md)
- [Token 与成本](audits/token-and-cost.md)
- [耗时](audits/latency.md)
- [得分与 verifier](audits/score-and-verifier.md)
- [交付链与过程收敛](audits/delivery-and-process.md)
- [FMEA 失败模式](audits/failure-modes.md)
- [首个 consequential break 与根因](audits/root-cause.md)

## 实现与交付

- [Harbor、BitFun 与 OpenCode adapter](adapters/harbor.md) 只定义 schema 探测和 provenance，不定义审计结论。
- [AEO AnalysisAgentAdapter](adapters/aeo.md) 定义结构化 facts/evidence 的准入、任务类型和 hypothesis 输出边界。
- [聚合与跨组比较](aggregation.md) 是所有跨 trial 汇总的唯一规范来源。
- [报告与机器输出](reporting.md) 是交付结构、机器字段和中文报告模板的唯一规范来源。

## 术语

- `measurement`：全量、同口径事实或指标。
- `mechanism`：深读证据支持的行为机制，不代表发生率。
- `candidate`：自动规则命中的待复核信号。
- `finding`：复核后确认、排除或保持未知的结论。
- `cohort`：满足共同身份、baseline、机制和证据要求的严格聚合组。
- `theme cluster`：跨任务的相似主题，只用于发现模式，不用于严格因果或发生率推断。
