# 证据与可分析性

## 五层证据

1. **原始事实**：文件、hash、字段、step、tool call、observation、patch、verifier assertion。
2. **派生指标**：duration、token、计数、配对差、覆盖率；必须携带 provenance。
3. **启发式候选**：正则或结构规则命中的信号，状态固定为 `heuristic`。
4. **人工裁决**：对 candidate 作 `confirmed|rejected|indeterminate` 判断。
5. **因果假设**：经过替代解释、反证和反事实检查的机制说明。

后层不得掩盖前层缺失。现有报告可以定位，不能替代原始 artifact。

## Provenance

每个派生字段至少记录：`source_path`、`source_field`、`adapter`、`status`、`confidence`。关键 artifact 记录绝对路径、字节数和 SHA-256；超过 hash 阈值时记录阈值与跳过原因。

多个来源冲突时保留原值和来源，不静默选择。只有相同 candidate patch 被独立复核且有 hash/provenance 时，才把变化后的 verifier 值称为 reconciled truth。

## 整体 Health

- `valid`：支持当前结论的身份、trace、delivery、verifier 和相关指标完整且一致；reward 可以为 0。
- `degraded`：有缺失、截断、未知 schema 或 provenance 异常，但仍支持部分判断。必须列出影响的问题。
- `infra_failed`：基础设施使 trial 没有形成可评估行为。它是执行状态，不是行为根因。
- `behavior_unverified`：存在行为或 patch，但 verifier 未运行、未覆盖目标行为或无法独立验收。

## 逐维度 Coverage

对 identity、trace、delivery、verifier、environment、integrity、tokens、latency 分别记录：

- `complete`：当前问题所需证据齐全且一致。
- `partial`：能作有限结论，且可说明缺失影响。
- `absent`：没有可用证据。
- `contradictory`：权威来源冲突且无法可靠对账。
- `not_applicable`：该维度不适用。

整体 health 不替代专项 coverage。Token 完整不意味着可做耗时分解；trace degraded 也不必然阻止 score 对账。

## 准入决策

对每个用户问题填写：所需维度、实际 coverage、允许的结论强度、缺失影响。`complete` 可作确定判断；`partial` 必须带限制；`absent` 不作该类结论；`contradictory` 只报告冲突和解决条件。

对 `degraded` trial 仍尝试回答证据允许的问题。只有关键 reasoning、patch 或 verifier 缺失到无法闭合因果时，才停止根因归因。

## 安全与脱敏

配置只提取 allowlist：agent/runtime、model、environment type、timeout、网络策略标识和资源限制。API key、Authorization、cookie、密码、token、完整环境变量和 credential URL 默认脱敏。

命令与 observation 只保存证明候选所需的短摘要；长日志保留路径和 step，不复制到报告。脱敏前的敏感值不得进入生成物、测试 fixture 或错误消息。

## Raw 与 Reconciled Truth

- 保留 result 中的原始 reward、独立 verifier reward、raw/back-up result 和 reconciliation 元数据。
- 同一值复制到两个文件不算独立复核。
- Agent final response、Todo completed、本地测试或 patch 形状不能替代 verifier truth。
- 无法解释的 score 差异把 verifier coverage 标为 `contradictory`，而不是选择更有利的值。

## 完成检查

- 输入目录未被写入，输出不位于输入内部。
- Trial 清单没有按 outcome 隐式过滤。
- 缺失值保持 `null`，没有转成 0。
- 每个后续结论有对应 coverage 和 provenance。
- 生成物未包含未脱敏凭证。
