# 聚合与跨组比较

## 聚合对象

在聚合前标明结论层级：

- **Full-population measurement**：全量、同口径抽取的 outcome、health、coverage、token、duration 或 candidate 计数。
- **Adjudicated finding**：人工复核后的环境、完整性、FMEA 或根因结论。
- **Sample mechanism**：确定性深读样本揭示的机制，只描述所选样本。
- **Hypothesis**：尚未通过对照或实验验证的解释。

任何图表、比例或摘要都必须标明所属层级。

## 分母纪律

每项统计记录总体、纳入条件、排除条件、有效 n、缺失 n 和统计单位。Trial-level、test-level、event-level、request-level 不得混用。

- Health 分母：全部枚举 trial。
- 专项 coverage 分母：全部 trial，并单列各 coverage 状态。
- 专项 finding 率：满足该专项准入且已裁决的 trial。
- 根因分布：仅 `full` 模式下全部可分析失败；无法归因项保留在分母或单列，不能静默删除。
- 配对统计：仅 `strict|conditional` pair，并分别报告等级构成。

缺失值不计为 0。若不同 adapter、runtime 或 evaluator 口径不能对齐，拆表或降为描述性结果。

## Strict Cohort

严格 cohort 同时要求：

- 共同 task checksum 和 baseline，或已有明确的严格等价证明；
- 相同 verifier 版本/指纹和验收契约；
- 相同主分类、窄 mechanism key 与关键代码机制；
- Reasoning、patch、verifier 证据完整且归因粒度一致；
- 没有明显反证。

只共享 `patch_decision`、失败测试名或 reward 不能构成 cohort。不同任务的相似机制只能形成 `theme cluster`，用于提出控制和后续实验，不用于严格发生率或因果比较。

## 对照与不确定性

失败 trace 用于定位断点，成功 trace 用于验证该机制是否区分结果。配对连续指标报告中位数、配对中位差/比和固定种子 10,000 次 task bootstrap 95% interval；二元结果报告四象限和通过率差区间。

小样本、异质任务、删失或多重比较存在时，优先表达区间和限制，不默认输出 p 值。观察性比较只使用“观察到”“与……一致”，不写单变量因果优越性。

## 聚合流程

1. 冻结 trial 清单、methodology/rule/schema 版本和 selection。
2. 对每个指标确定单位、分子、分母、缺失和比较资格。
3. 分开计算 full measurement、candidate 和 adjudicated finding。
4. 只在严格条件满足时建立 cohort；其余归主题聚类或未决项。
5. 用成功控制和反证挑战机制解释。
6. 对建议的控制给出目标 failure mode、验收指标和 paired A/B 设计。

## 禁止推断

- 不从深读样本外推全量机制比例。
- 不把 candidate count 当 confirmed finding count。
- 不把测试失败数当独立缺陷数。
- 不把跨任务主题聚类称为同机制 cohort。
- 不把 token/time 相关性称为性能或推理能力的因果解释。
- 不把 RPN 当概率，也不跨不兼容 rubric 比较。

## 输出与完成检查

机器输出保留每项统计的 numerator、denominator、unit、eligibility、missing、method、seed 和 interval。正文先报告健康与结果，再报告专项 finding、机制、cohort 和未决替代解释。

完成前逐项回答：这个数字来自全量还是样本；分母是什么；缺失如何处理；比较资格是什么；能否下钻到 trial；是否超过证据允许的因果强度。
