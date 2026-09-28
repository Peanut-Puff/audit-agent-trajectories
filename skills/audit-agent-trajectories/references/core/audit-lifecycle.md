# 审计生命周期

## 0. 定义问题

记录输入、输出目录、分析日期、用户关注点、单 trial/单 job/配对模式和 `metrics|standard|full` 深度。把问题改写成可证伪的审计问题，例如“有多少 trial 因 provider 故障没有形成可评价 patch”，而不是“模型为什么不稳定”。

退出条件：范围、交付物、分母和停止条件明确。

## 1. 清点证据

枚举全部 trial，不依据 reward 或已有报告筛选。记录 result、config、trajectory、patch、verifier、usage、raw stream、reconciliation 和环境日志的路径、大小、hash 与缺失状态。原始目录只读。

退出条件：机器清单行数等于实际枚举数，任何过滤都有显式理由。

## 2. 归一化

选择 adapter，保留原字段和来源，把身份、score、usage、duration、event、delivery 映射到统一记录。未知或矛盾值保持 `null`/`contradictory`，不使用猜测补齐。

退出条件：每个派生字段可以回溯到 source path、field、adapter、解析状态和置信度。

## 3. 可分析性准入

按 [证据与可分析性](evidence-and-readiness.md) 判定整体 health 与逐关注点 coverage。明确当前证据可以回答、只能部分回答和不能回答的问题。

退出条件：所有后续结论都有相应 coverage；不足时降低结论强度或停止该分支。

## 4. 可比性准入

只有涉及两个以上 trial/job 时执行。按 [可比性与抽样](comparability-and-sampling.md) 检查任务身份、baseline、verifier、运行预算和 telemetry 口径，给出 `strict|conditional|descriptive_only|ineligible`。

退出条件：每个 pair 有等级和理由，统计总体不含不合格样本。

## 5. 全量测量与确定性选择

先完成全量 outcome、health、coverage、资源和候选计数，再写 selection manifest。`standard` 深读确定性失败样本和成功对照；`full` 覆盖全部可分析失败；`metrics` 不进入行为归因。

退出条件：全量 measurement 与深读 sample 在数据和报告中明确分开。

## 6. 专项审计

只加载当前问题对应的专项文档。每个专项先核对自身准入证据，再按文档规定生成指标、候选和待裁决问题。自动规则止于 candidate。

退出条件：候选有原始证据路径和 step；没有把信号升级为结论。

## 7. 深读与裁决

对选中 trace 重建紧凑事件账本：任务契约、关键观察、mutation、validation、persistence、capture、verifier。逐项确认或排除 candidate；失败归因还需成功对照、替代解释和反事实复核。

退出条件：finding 有直接证据、状态、置信度、局限和最强替代解释。

## 8. 聚合

按 [聚合与跨组比较](../aggregation.md) 声明分母、缺失、比较资格和不确定性。严格 cohort 与主题聚类分开；样本 mechanism 不外推为全量率。

退出条件：每个比例能追溯到分子、分母、排除项和口径。

## 9. 报告 QA

按 [报告规范](../reporting.md) 生成机器索引和中文报告，检查脱敏、行数、链接、hash、人工文件保护和语言边界。重要结论区分“观察到”“与……一致”“无法区分”。

退出条件：另一位分析者可使用 manifest、命令、selection 和证据路径复核结论。
