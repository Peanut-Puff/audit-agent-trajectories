# 得分与 Verifier 审计

## 审计问题

Verifier 实际验收了什么，raw 与 reconciled truth 是否一致，F2P/P2P/N2P/S2P 和 phase 结果说明哪类新增能力或回归。

## 准入条件

至少需要权威 reward 或 verifier report。只有 agent final response、本地测试或 patch 时属于 `behavior_unverified`，不能声明通过。Reward、CTRF 和 phase logs 冲突时 verifier coverage 为 `contradictory`。

## 证据来源

- Result 中的原始 verifier reward、独立 `verifier/reward.json`。
- Recheck/reconciliation manifest、candidate patch hash 和环境 provenance。
- CTRF、测试源码、XML/report、stdout、stack、snapshot 和 run/test/fix logs。
- Agent 本地测试与 final claim，只用于比较验证范围，不作为 verifier truth。

## 指标与语义

- `reward`：当前 verifier 的总通过判定。
- `partial`：按 evaluator 定义的部分分数，不假设统一公式。
- `F2P`：任务目标行为是否从 fail 转 pass。
- `P2P`：基线通过行为是否回归；先确认 transition map 有效。
- `N2P/S2P`：新增启用或原跳过行为，单独报告。
- `run/test/fix`：区分 baseline、test patch 激活和 candidate effect。

## 审计步骤

1. 保留 raw reward，再检查独立 verifier 与 reconciliation。
2. 只有相同 patch 被独立复核且 hash/provenance 完整时采用 reconciled truth。
3. 读取 CTRF 和 phase logs，验证计数、测试身份和 transition map。
4. 对每个失败测试回答：构造状态、期望、实际、执行路径、最终最小致因代码和证据边界。
5. Hidden test 不可见时只陈述测试名/assertion 能证明的事实，示例标为“等价示意”。
6. 将多个失败按共同代码机制合并，不用测试条数代替缺陷数。

## 聚合规则

按 raw/reconciled、trial/test/event 层级分别标记计数。配对报告共同 pass/fail、A-only 和 B-only；不同 verifier 指纹或任务版本不得进入严格得分比较。零测试单列，不自动归为 agent 行为失败。

## 禁止推断

- Final response、自测通过、Todo completed 不等于 verifier 通过。
- F2P 失败不自动说明功能完全缺失；先看通过项和失败机制。
- P2P 派生分数没有 transition map 时不能直接称为回归。
- `false !== true` 等摘要不能证明 parser crash 或完整输入。
- Verifier endpoint 是结果，不自动是根因。

## 输出与完成检查

输出 raw/reconciled score、reconciliation 依据、各 transition 计数、失败测试解释、测试源码可见性和证据限制。确认每个结论明确使用哪个 verifier 版本和 candidate patch。
