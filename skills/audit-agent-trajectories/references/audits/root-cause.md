# 首个 Consequential Break 与根因归因

## 审计问题

哪个最早的 agent 可控决策偏离了当时仍可行的正确路径，并被后续 plan/patch 继承，最终造成 verifier 观察到的缺口。

## 准入条件

根因归因至少需要任务契约、最终 patch 和 verifier 后果；要判断认知起点还需要 reasoning/plan/tool result。只有 reward 或测试名时不作确定主因。`infra_failed` 且未形成行为产物时不强行归因。

## 主分类

- `requirements_understanding`：首次错误发生在题面契约、边界、优先级或兼容要求的解释。
- `code_localization`：行为放入非权威路径，局部实现无法触达目标执行链。
- `patch_decision`：需求和位置基本清楚，但算法、状态机、数据结构、兼容或错误策略不能满足契约。
- `subagent_dispatch`：任务拆分、分派范围或依赖顺序首次造成关键遗漏。
- `subagent_adoption`：已有可用子任务结果，但主 agent 未取回、误读或错误合入。
- `context_forgetting`：有前后证据证明长上下文或 compaction 后丢失已掌握约束。
- `repeated_exploration`：无新增信息的重复探索直接挤占关键实现或验证。
- `write_conflict`：并发或后续写覆盖、丢失或错误合并已完成行为。
- `tool_unobservable`：必要 tool result 缺失/截断，并与后续错误决策闭合因果。
- `repeated_failure`：同一失败多次出现且未改变假设或方法，最终仍因此失败。

`infra_failed` 是健康状态。`architecture`、`incomplete implementation`、`verifier failed`、`edge case` 是结果或宽泛描述，不是合格主分类。

## 首错四条件

一个节点必须同时满足：

1. **可控制**：属于 agent 的解释、选择、采纳或行动。
2. **可行动**：当时已有足够证据采取更正确做法。
3. **有因果**：被后续 plan/patch 继承并导致最终缺口。
4. **可证明**：有 reasoning、tool result、Edit/Write、patch 或 verifier 证据。

认知层优先于时间编号：`错误理解 -> 错误定位 -> 错误方案承诺 -> 错误实现 -> 漏测 -> verifier 暴露`。前层无证据时使用最早可证层并降低置信度。

## 审计步骤

1. 把题面拆成契约矩阵：行为、边界、错误、优先级、兼容性和验收条件。
2. 从 verifier 失败反向定位最终 patch 的最小致因代码和数据流。
3. 沿 trajectory 找首次引入同一错误语义的 Edit/Write；展示 3-20 行原始关键代码。
4. 检查该实现之前及同 step 的题面转述、reasoning、plan、tool result 和 subagent 建议，回答为什么会写出该代码。
5. 区分“代码为什么失败”和“agent 为什么选择它”。没有直接动机证据时写“形成路径可证、动机不可证”或“思想起点不可证”。
6. 选择唯一主分类和窄机制键，列出 secondary factors。
7. 提出最强替代分类，用反证和反事实复核；失败机制、代码成因和最终归因分别给置信度。

## 需求理解与补丁决策

错误方案形成前没有准确表达关键契约，且错误转述塑造了方案，归 `requirements_understanding`。Agent 已明确知道要求和正确机制方向，却选择不能满足它的实现策略，归 `patch_decision`。

准确抄写名词或列表不自动证明理解了封闭性。封闭白名单、精确匹配或明确优先级被当作开放示例，通常是需求理解；若 reasoning 明确认知封闭边界后仍因算法/兼容策略扩展，才是补丁决策。

## 机制键

优先使用：`boundary_handling`、`api_compatibility`、`error_handling`、`async_lifecycle`、`parser_serialization`、`state_cache_consistency`、`integration_wiring`、`regression_compatibility`、`test_scope_or_validation`、`provider_or_tooling`。证据不足写 `unspecified`。

`completion_gate_requirement_coverage` 只有在错误验收策略是最早、可行动且直接决定错误 delivery 被接受时才能作为主因；更早已有误读、定位或补丁错误时，它是 secondary factor。

## 证据强度

- **强**：题面、明确错误取舍、Viewer step、关键代码和 verifier 后果闭环。
- **中**：Reasoning 不完整，但 plan/Edit、patch 与失败可复现。
- **弱**：只有最终 patch 与有限 verifier 摘要；只给机制假设并降低置信度。
- **不足**：只有 reward/失败计数或多个机制无法区分；不作确定主因。

## 聚合与禁止推断

每个失败 trial 最多一个主分类，但可有多个 failure mode 和 secondary factor。只有完整模式覆盖所有可分析失败后，才聚合主因分布；严格 cohort 规则见 [聚合](../aggregation.md)。

不得把测试条数当根因条数，不得从测试名虚构输入，不得把实现行自动当认知起点，不得用成功 trace 的代码当唯一正确答案，也不得把 post-run verifier 无返修机会写成漏检原因。

## 输出与完成检查

每个可分析失败记录：任务契约、失败测试、最小致因代码、首个实现 step、为什么这样写、唯一主分类、机制键、替代分类、反证、反事实、secondary factors、成功对照、分项置信度和证据限制。

短链固定为：`题面契约 -> 首错 reasoning/plan -> 首个可证实现 -> 最终致因代码 -> verifier 后果 -> 归因复核`。
