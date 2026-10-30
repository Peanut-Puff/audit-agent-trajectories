# 轮次归一化与分类

## 适用范围

当问题涉及模型轮次、工具调用、探索/编辑/验证分布或 E/B/I/V/P 阶段时，先生成跨 adapter 的最小事件账本，再按需运行独立分类器。脚本输出是 measurement 或 heuristic projection，不解释质量、动机或根因。

## 默认阶段口径

- 整个 Job / 配对 Job：首选 E/B/I/V/P，便于全量阶段统计和跨任务概览；保留 heuristic、缺失与不确定边界。
- 单 Trial / 一对 Trial / Job 下钻详情：默认使用[人工语义时序](semantic-trial-analysis.md)，按真实工作目标、方案实验、集成、测试返修和交付细分。自动 E/B/I/V/P 只作辅助依据，不能替代深读。
- `metrics` 只输出确定性指标与明确标记的 heuristic，不推断语义或补写机制；用户显式要求的口径优先。

## 事件归一化

```bash
python3 scripts/normalize_trajectory_events.py INPUT [INPUT ...] \
  --output /absolute/path/to/normalized-events
```

支持规范化 Harbor trial/job、解压后的 AEO case-log 和原始 case-log ZIP，并归一化 BitFun request traces、OpenCode event log 与 `agent/trajectory.json`。

默认 `compact` 只输出：

```text
summary.json
trajectory-events.jsonl
```

事件包用 `record_type=manifest|trial|round|tool_call` 区分记录。需要拆分 JSONL、CSV 镜像和 trial 清单时显式加 `--output-level full`。输出不复制 prompt、reasoning、命令、参数或 observation；命令和目标只保存短 SHA-256 fingerprint，原始证据通过路径、ZIP member、session、round 和 tool ID 定位。

## 动作分类

```bash
python3 scripts/classify_round_actions.py /path/to/normalized-events \
  --output /absolute/path/to/round-actions
```

互斥分类完全采用 BitFun 仓库 `scripts/diagnostics/analyze-agent-case-logs.py` 的口径；该脚本是分类语义的权威来源：

`verification > editing > exploration > other`

默认只输出 `round-actions.json`，同时包含 manifest 和 job summary。需要逐轮结果时加 `--include-rounds`。

混合编辑验证轮归入 verification；多标签仍保留在逐轮 `operation_tags`。Poll/Wait/WriteStdin/TodoWrite 归 other，结构化 `validationKind`/`validationClassification` 优先补充验证标签。四类互斥且穷尽，类别之和等于总轮次。分类描述同一模型 response 的可观察工具组成，不证明模型意图。

## Stage 投影

```bash
python3 scripts/classify_round_stages.py /path/to/normalized-events \
  --output /absolute/path/to/round-stages
```

- `E`：探索，直到编辑前 baseline 验证或首次 mutation。
- `B`：首次 mutation 前的 baseline 验证窗口；没有编辑前验证时缺席。
- `I`：从首次 mutation 到首次 mutation 后 validation 之前。
- `V`：从首次 mutation 后 validation 到 stable green；没有 stable green 时延续到结束。
- `P`：stable green 后的继续工作。

Stable green 是最后一个失败/未知 validation 之后，后续 validation 全部成功时的第一个成功 round。输出默认只有 `round-stages.json`，包含 manifest、job summary 和逐 trial/session 边界；逐轮 stage 需加 `--include-rounds`。

Stage 是根据 mutation/validation 事件投影的启发式边界，不是 runtime 原生 phase。临时 probe、管道掩盖 exit code、未知 validation 结果或日志缺失都会影响边界；比较时必须同时报告无法形成 B/P 的 trace 数和 unknown validation 数。

临时编译实验、lint 成功或 shell exit=0 不能称为任务已经验收完成。确认“首次全库通过”“最终候选验证通过”等里程碑时必须读取具体命令、检查范围、完整相关诊断与后续修改；自动 stable-green 不提供这层保证。

## 完成检查

- Model round 与 tool call 分开计数。
- Adapter 原生 request 边界可由 source 下钻。
- 混合编辑验证只占一个互斥 round 类别。
- 默认输出保持 compact，只有下钻需要时才生成逐轮分类。
- 分类、stage、failure surface、责任候选和 root cause 保持不同结论层级。
