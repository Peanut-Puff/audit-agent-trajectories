# 耗时审计

## 审计问题

Trial 的时间花在哪些阶段，完成和超时样本是否可比较，慢是否来自模型、工具、验证、恢复还是基础设施等待。

## 准入条件

Wall-clock 至少需要可信 started/finished 时间。阶段分解需要 typed phase 或 event start/end；只有相邻 step timestamp 时不得冒充 tool/model duration。Timeout/cancelled 作为右删失或终止样本。

## 证据来源

- Result 的 setup、agent execution、capture、verifier 起止时间。
- Typed model request、tool execution、test、wait/recovery 事件。
- Trajectory 中 first mutation、last mutation、validation 和 final response timestamp。
- Timeout budget、取消原因、worker/provider 等待日志。

## 指标

- `wall_duration`、setup、agent execution、model wait、tool execution、validation、recovery/wait、capture、verifier。
- `time_to_first_mutation`、`last_mutation_to_validation`、`finalization_duration`。
- `completed|right_censored|terminated_unknown` 状态。

没有 typed timing 的阶段保持 `null`。Phase 总和与 wall-clock 不一致时记录重叠、并发或未知时间，不强行归一到 100%。

## 审计步骤

1. 验证时间戳时区、单调性、开始/结束和预算。
2. 标记正常完成、timeout、取消和异常终止。
3. 只在有 typed 边界时分解阶段；列出未解释时间。
4. 对慢样本检查重复探索、等待、重试、长测试和基础设施聚集。
5. 对配对样本检查 timeout、资源、并发和 telemetry 口径一致性。
6. 将耗时现象与行为机制分开；需要因果时进入 delivery/process 或 environment 审计。

## 聚合规则

普通完成耗时只包含双方正常完成且口径一致的样本。Timeout/cancelled 单列数量、删失下界和取消前状态；不得混入普通均值。报告中位数、P90、配对中位差和有效/缺失数。

## 禁止推断

- Timeout 不等于 agent 一直无进展，也不自动是环境故障。
- Exit 137 不自动是 OOM。
- Step 间隔不等于某个 tool 的执行时间。
- 慢且失败不证明时间浪费；任务难度是混杂因素。
- 不比较不同预算或删失规则下的普通均值。

## 输出与完成检查

每个 trial 输出完成状态、wall-clock、可证阶段、删失信息和 provenance。聚合明确 completed 与 censored 分母，列出未解释时间和口径差异。
