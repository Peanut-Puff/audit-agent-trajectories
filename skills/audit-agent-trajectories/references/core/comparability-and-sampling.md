# 可比性与确定性抽样

## 审计问题

判断两个 trial 是否测量同一任务契约，以及跨 job 差异能否进入配对统计。目录名和随机 trial 后缀不构成身份。

## 配对等级

- `strict`：task checksum、baseline 和 verifier 指纹均存在且一致。
- `conditional`：task 名称和 verifier 指纹一致，且 checksum、baseline、题面指纹至少一项一致；不一致或缺失项必须列出。
- `descriptive_only`：只有同名或不完整语义证据，允许并列描述，不进入配对区间估计。
- `ineligible`：task 名称不同，或已知 baseline、题面、verifier 语义冲突。

Checksum 不同不得严格配对，但必须继续检查 baseline、题面和 verifier 后再决定其余等级。

## 影响解释的配置差异

记录 model、agent/runtime、provider、timeout、网络策略、硬件、并发、重试和 telemetry 口径。它们不会自动取消任务配对，但会限制把差异归因给单一模型或 agent。

## 单 Job 标准抽样

- 失败不超过 12 个时深读全部失败。
- 否则按 verifier endpoint、任务族和健康/完整性风险轮转选择 12 个失败，最终以 task name、trial ID 稳定排序。
- 最多加入 4 个成功对照，优先来自失败代表的任务族，再选择 effort 中位项。

`metrics` 不做深读；`full` 深读所有 `valid|degraded` 失败，并为受影响任务族选成功控制。`infra_failed` 且无行为产物时不强行归因。

## 配对标准抽样

目标为 8 个任务对：4 个 outcome flip、2 个共同失败、2 个共同成功。Flip 尽量同时覆盖 A-only 和 B-only；共同失败优先不同 verifier endpoint 或任务族。

某层不足时从剩余合格 pair 稳定补位，并将 fallback 写入 `selection.csv`。选择清单必须先于深读生成，包含候选总体、规则版本、排序键、选择和排除理由。

## 配对统计

- 只有 `strict|conditional` pair 进入区间统计，等级构成分别报告。
- 二元结果报告 A-only、B-only、共同 pass、共同 fail 和配对通过率差。
- 连续指标报告双方中位数、配对中位差和配对中位比。
- 默认用固定种子、10,000 次按 task pair 重采样的 percentile 95% interval。
- 每个指标逐项排除缺失，报告 `n_available` 和 `n_missing`；timeout/cancelled 不进入普通完成耗时比较。
- 默认不输出 p 值，不把观察性差异写成因果优越性。

## 禁止推断

- 不用同名任务冒充严格配对。
- 不用深读样本估计机制发生率。
- 不把跨 adapter 的非等价 token/duration 字段直接比较。
- 不因一侧缺失而把其值补为 0。
- 不把共同失败自动解释为共同根因。

## 输出与完成检查

`comparability.csv` 每行包含 pair、等级、理由、outcome quadrant 和各指标可用性；`comparison-stats.json` 记录 seed、抽样次数、有效/缺失数和区间。

完成前确认：输入顺序变化不改变 selection；每个统计样本都能回到 pair；所有 `descriptive_only|ineligible` 已从配对区间排除。
