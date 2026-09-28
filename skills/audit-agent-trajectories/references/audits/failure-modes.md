# FMEA 失败模式审计

## 审计问题

Evaluator 可观察到哪些失效模式，发生范围和检测难度如何，哪些控制可以直接降低相应风险。FMEA 不回答最早行为根因。

## 准入条件

候选可由全量结构化数据生成；正式 FMEA assignment 必须人工检查引用的原始证据。Occurrence 需要完整、同口径的全量总体；没有全量分母时不得评分。

## Failure Modes

| ID | 可观察失败模式 | 主要证据 |
| --- | --- | --- |
| FM-01 | Verifier 拒绝捕获的 delivery | reconciled reward/report |
| FM-02 | Hard deadline 或异常终止 | exception/termination log |
| FM-03 | 没有正常 final response | trajectory stop/final step |
| FM-04 | 正常 final response 但 verifier 失败 | final message + reward |
| FM-05 | Patch/artifact 缺失、空、陈旧或不完整 | delivery manifest/hash |
| FM-06 | F2P 目标行为未修复 | F2P transitions/tests |
| FM-07 | P2P/N2P/S2P 回归或 transition 异常 | valid transition map |
| FM-08 | 最终 mutation 后无可识别 validation | ordered event ledger |
| FM-09 | Final claim 强于 validation 证据 | final response + raw output |
| FM-10 | 无 mutation 的重复等价 validation | normalized command sequence |
| FM-11 | 高资源使用仍失败 | 同口径 token/time percentile |
| FM-12 | Usage/trace ledger 缺失或矛盾 | cross-ledger reconciliation |
| FM-13 | 相同 patch recheck 改变 outcome | reconciliation + hashes |
| FM-14 | Test/fix phase 捕获零测试 | phase summary/logs |

## 审计步骤

1. 用确定性规则生成 candidate，并保留 rule version 和证据路径。
2. 逐条检查它是否符合 mode 定义，排除 adapter 漏识别和日志文本误报。
3. 将同一 trial 的同一 mode 合并，保留事件数和代表证据。
4. 稳定 failure mode 和证据后才评分。
5. 每个控制必须对应可测 mode，并给验收指标；因果效果需要 same-task paired A/B 验证。

## FMEA 评分

`RPN = S * O * D`，只在声明的评分框架内排序：

- Severity：1 可忽略，3 可恢复低效，5 trial 失败，7 job/计量完整性风险。
- Occurrence：从全量 trial 计数映射到预先声明的 bins，并同时显示原始 count。
- Detection difficulty：1 typed event 直接暴露，3 需跨 artifact 对账，5 需深读或关键 telemetry 缺失。

同一审计内保持 S/D 标准稳定；不同 rubric 的 RPN 不互比，也不解释为概率。

## 聚合规则

一个 trial 可以有多个 failure mode。报告 trial-level 和 event-level 分母，不把二者混合；candidate count 与 adjudicated count 分开。FM-11 的高资源阈值只在同 job/同口径内定义。

## 禁止推断

- FM-01/06/07 是 endpoint，不是根因。
- 自动命中不等于确认 mode。
- 多个 FMEA mode 不代表多个根因。
- RPN 不证明发生概率或控制有效性。
- 正则未识别 validation 不证明没有验证。

## 输出与完成检查

输出 mode、trial/event count、S/O/D、RPN、证据、裁决状态、控制和验收指标。确认 occurrence 来自全量总体，candidate 未静默当 finding，控制没有超出证据支持的因果强度。
