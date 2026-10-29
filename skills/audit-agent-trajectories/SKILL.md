---
name: audit-agent-trajectories
description: 审计 Harbor、DeepSWE、Pier 或类似 coding-agent evaluation 的 trial/job 轨迹，先验证数据健康度与可比性，再分析环境、评测完整性、Token、耗时、得分、轮次行为、交付链和聚合根因。用于单 trial 诊断、单 job 全量审计或同任务跨 agent/model 配对比较；不用于代替缺失的 verifier 重跑，也不把启发式信号直接当作作弊或根因。
---

# Agent 轨迹审计

先完整阅读 [方法索引](references/methodology-index.md) 和 [审计生命周期](references/core/audit-lifecycle.md)，再按问题选择最小必要文档集。原始输入始终只读；输出目录不得位于输入目录内部。

## 执行入口

- 单 trial 始终使用 `full`；单 job 默认 `standard`；只要全量指标时使用 `metrics`。
- 配对 job 必须先做可比性准入。只有 `full` 覆盖全部可分析失败后，才能报告全量根因分布。

```bash
python3 scripts/audit_trajectories.py INPUT [INPUT ...] \
  --output /absolute/path/to/audit \
  --mode auto --depth standard --focus all --output-layout compact
```

需要跨 adapter 对齐 model round/tool call 时使用紧凑归一化器：

```bash
python3 scripts/normalize_trajectory_events.py INPUT [INPUT ...] \
  --output /absolute/path/to/normalized-events
```

脚本只生成事实、派生指标和 `heuristic` 候选。Compact 布局只交付 `audit.json`、`findings.jsonl` 和 `report.md`；环境责任、评测违规、FMEA 和根因必须复核原始证据后写入 findings，重跑不得覆盖 findings 或已有报告。

## 文档路由

- 所有任务：[证据与可分析性](references/core/evidence-and-readiness.md)；Harbor/BitFun/OpenCode 输入再读 [Adapter](references/adapters/harbor.md)。
- AEO `AnalysisAgentAdapter` 的结构化 facts/evidence 输入读 [AEO Adapter](references/adapters/aeo.md)；运行时方法来自该文档链接的版本化 profile，不要在宿主插件复制 prompt，也不要把裁剪后的 AEO Trace ZIP 伪装成 Harbor Trial 目录。
- 环境或作弊：[环境](references/audits/environment.md) 或 [评测完整性](references/audits/evaluation-integrity.md)。
- Token、成本或耗时：[Token 与成本](references/audits/token-and-cost.md)、[耗时](references/audits/latency.md)；跨 trial 时再读 [聚合](references/aggregation.md)。
- 得分或 verifier：[得分与 verifier](references/audits/score-and-verifier.md)。
- 探索/编辑/验证轮次或 E/B/I/V/P 阶段：[轮次归一化与分类](references/audits/round-analysis.md)；跨 trial 时再读 [聚合](references/aggregation.md)。
- 失败归因：[交付与过程](references/audits/delivery-and-process.md)、[失败模式](references/audits/failure-modes.md)、[根因](references/audits/root-cause.md)。
- 配对比较：[可比性与抽样](references/core/comparability-and-sampling.md) 和 [聚合](references/aggregation.md)。
- 交付前完整阅读 [报告规范](references/reporting.md)。
- 用户需要 HTML 时读 [独立展示层](references/html-presentation.md)；显式 `--html` 附加 Trial/Job 总览和静态详情，筛选同步分母与结论范围，AEO 仍返回 JSON。

## 强制边界

- 缺失保持 `null`；未知 schema 降级；所有派生值保留 provenance；默认脱敏凭证和敏感环境值。
- 健康、结果、失败模式和根因是不同结论。URL 文本、正则命中、timeout、Exit 137、本地测试通过或 final claim 都不能单独证明原因。
- Cached prompt tokens 不重复计入 input；跨 adapter 只比较语义等价且双方有值的字段。
- 标准模式的深读样本不得外推为全量机制发生率；比较必须报告资格等级、有效样本数、缺失数和不确定性。
