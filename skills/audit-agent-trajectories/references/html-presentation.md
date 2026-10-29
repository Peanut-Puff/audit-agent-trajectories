# HTML 展示层

HTML 是显式启用、可重建的附加输出。事实仍来自 `audit.json` 或 expanded 的 generated 文件；裁决仍来自人工 `findings.jsonl`。渲染器不生成根因，不读取完整原始轨迹，不覆盖 findings 或 `report.md`。运行时只依赖 Python 3.10+ 标准库；CSS、JS 和当前页面数据嵌入 HTML，不访问 CDN。Job 详情以相邻静态目录交付。

## 单 Trial、Job 与配对输入

提取时加 `--html`：

```bash
python3 scripts/audit_trajectories.py /path/to/trial \
  --output /path/to/audit --output-layout compact --html
```

也可独立渲染已有审计，不必重跑提取器：

```bash
python3 scripts/render_audit_html.py /path/to/audit \
  --output /path/to/audit/report.html

python3 scripts/render_audit_html.py /path/to/left-audit /path/to/right-audit \
  --normalized /path/to/normalized-events \
  --annotations /path/to/presentation.json \
  --output /path/to/pair-report.html
```

输入可为 compact 审计目录、`audit.json` 或 expanded 根目录。`mode=job` 或多于两个 Trial 自动生成 Job 总览；接受一份 paired 审计或两份单 Job 审计生成双 Job 比较。单 Trial 和一对 Trial 使用原视图。Trial key 必须唯一，身份冲突不做自动改名；不把两份 paired 审计合成四组。

```bash
python3 scripts/audit_trajectories.py /path/to/job \
  --output /path/to/audit --output-layout compact --html

python3 scripts/render_audit_html.py /path/to/left-job-audit /path/to/right-job-audit \
  --output /path/to/report.html --annotations /path/to/presentation.json
```

Job 交付包含 `report.html` 与 `report-details/`，后者预生成 Trial 与配对详情页。首页只嵌入紧凑指标、coverage、选择状态和有界发现摘要，不嵌入逐请求轨迹；详情页保留原有蓝橙曲线、轮次/耗时/token 阶段条与按需依据。详情路径使用稳定 hash，链接返回 Job 总览。分享或移动报告时一起保留同名详情目录。

同一目录切换布局后若同时存在两套机器文件，独立渲染必须显式传入 `audit.json` 或 `generated/manifest.json`，避免选择过期数据；提取器的 `--html` 自动使用本次布局。

`--normalized` 接受[事件归一化器](audits/round-analysis.md)的 compact 或 full 目录。提取器的对应选项为 `--html-normalized`、`--html-annotations`，均要求 `--html`。没有事件账本仍能展示 Trial 总账、健康、verifier 和交付链；所选指标缺少逐请求数据时显示缺失，不画虚构曲线；没有人工标注则保留语义阶段空缺。

## 阅读结构与证据纪律

采用“总览 → 专项 → Trial → 证据”的导航与下钻结构：

- 首屏先给范围、方法版本、深度、结果和可信范围。健康与结果独立计数，`infra_failed` / `behavior_unverified` 不伪装成 verifier outcome，不做综合健康分或雷达图。
- 单 Trial 展示任务契约、raw/reconciled verifier、测试覆盖、语义阶段和交付链；成功不强行定位主失败。字段缺失仍显示未知。
- 配对先给 `strict|conditional|descriptive_only|ineligible` 与理由。只有前两类允许差值；指标各自显示有效/排除 n 和排除原因。未知结果不进入“共同失败”。单 pair 不生成总体效果区间。
- 每个数字连接口径、单位、有效分母、缺失/排除和 Trial。Finding 连接“事实 → 直接证据 → 裁决/解释 → 替代解释 → 置信度与限制”，保留首错决策、关键实现与 verifier 后果。
- 依据按需打开说明卡，不在正文铺陈逐请求索引。默认先读中文摘要，路径和原始字段收进“技术详情与来源”；关闭后返回原阅读位置，已有证据锚点仍可直达。
- 环境事实与责任判断、完整性候选与裁决、失败模式与根因分别保留。完整性不使用统一的绿色安全标记；未观察到证据不证明没有问题。
- `metrics` 只展示确定性指标与启发式候选，隐藏人工解释和语义标注，包括页面内嵌证据。`standard` 的机制只适用于深读样本；`full` 仍需证据闭环，单 Trial 页面不生成根因分布。

视觉采用浅灰背景、白色卡片、深蓝正文与蓝色/陶土橙对照。Trial 曲线使用单图下拉切换，固定保留“累计输入 Token、单次请求输入长度、累计输出 Token、累计 Reasoning、累计未缓存输入”五项，默认累计输入；请求序号/执行时间切换、悬停、键盘定位与证据下钻共用。没有某项记录时保持选项可选并显示缺失，不能补零。多 session 保留独立序列，不拼接成虚构时间线。

累计曲线只累加已观察输入，缺失请求处断线，后续明确标为已观察小计。未证明缓存包含关系时称“报告输入”，不能称完整上下文；cache 不重复加入。Token 差值额外要求双方 complete、缓存语义已声明一致、adapter 与账本来源一致；跨 adapter 暂只并列描述。超时、取消或完成状态未知不进入完成耗时差值。费用只展示账本与来源，不自动补价格。

输出、Reasoning 和未缓存输入分别累计，缺失与断线各自记录；Reasoning 不重复加入输出。未缓存输入仅在 `includes_cache` 下使用非负的输入减缓存读取，`excludes_cache` 下使用报告输入；缓存关系未知、读取数缺失或大于输入时不推算。

## 可选人工展示标注

`trial-presentation/1` 是独立展示输入，不能修改机器事实或替代 Finding。示例为合成占位值，实际 round key 从归一化事件读取：

```json
{
  "schema_version": "trial-presentation/1",
  "trials": {
    "job/task": {
      "input_token_semantics": "includes_cache",
      "evidence_refs": ["/absolute/source/usage.json#input-definition"],
      "task_contract": "实现目标与验收条件的有界摘要",
      "verifier_explanation": "输入、预期、实际与证据限制",
      "round_elapsed_sec": {"job/task/main/000001": 1.2},
      "semantic_stages": [
        {
          "title": "查询接通",
          "goal": "让查询路径满足任务契约",
          "actions": "连接入口与核心实现",
          "result": "定向断言通过",
          "round_keys": ["job/task/main/000001"],
          "duration_sec": null,
          "anomalies": "无已裁决异常",
          "evidence_refs": ["/absolute/source/events.json#round-1"],
          "annotation_method": "manual",
          "uncertainty": "只覆盖已列出的请求"
        }
      ]
    }
  }
}
```

`input_token_semantics` 只能为 `includes_cache|excludes_cache|unknown`，从原始账本确认，不凭 adapter 名猜测。`round_elapsed_sec` 必须指向已知 round、非负、会话内单调，并提供来源；显示的全部请求均有时间时才启用执行时间轴。否则默认请求序号，不按轮次插值时间。

语义阶段须有 `round_keys`、`annotation_method` 和 `evidence_refs`。同一请求不得重复计入多个语义阶段；未知 key 或重叠标注报错。可选 `alignment_key` 在同一 Trial 内须唯一，明确两侧阶段对应关系；否则只对齐两侧唯一的同名阶段，重复名称分列，不按顺序猜测对应。

阶段首屏按 **轮次 → 耗时 → token** 展示蓝橙横条与实际值；每项指标在所有阶段共用刻度，条长表示实际消耗。只有配对及该指标口径满足时显示差值/倍数；缺失保留空缺，部分输入使用斜线并标明缺失轮数。单 Trial 使用同一组件展示阶段内用量。目标、关键动作、结果、异常和标注限制按需展开。自动 E/B/I/V/P 仍在依据中注明 heuristic、边界和来源。辅助/未归属请求、请求 token 与 Trial 账本差额另列；差额不直接解释为浪费。未解释时间保持未知，重叠生命周期 phase 不相加。

现有 Findings 至少用 `trial_key` 关联；缺少对应身份的记录计数并排除，不猜测归属。展示支持 `finding_id`、`candidate_ref(s)`、`focus`、`finding_type`、`adjudication`、`status`、`summary`、`observation`、`direct_evidence`、`evidence_paths`、`interpretation`、`alternative_explanations`、`confidence`、`limitations`、`analyst`、`timestamp`，以及根因的 `first_error_decision`、`key_implementation`、`verifier_consequence`。没有字段时不补做分析，未知字段不整体嵌入 HTML；完整原文留在人工文件。

可选 `conclusion_level=sample_mechanism|hypothesis` 分别标注样本机制与假设；其余记录按已有 adjudication 展示已裁决发现或未裁决记录，不因被引用而提升结论等级。

## Job 总览与筛选

Job 首屏给出双方或单方的结果、health、范围与深度，再显示当前关注任务和最多五条有界发现。轮次、完成耗时、输入、账本费用提供直方分布、中位数及有效/缺失/排除 n；双方直方图区间共用刻度。数据覆盖按维度汇总，点击查看 Trial × 维度矩阵。任务列表每页 25 条，验证失败优先，提供独立 Trial/配对详情。

双 Job 先检查配对等级，保留不合格和无对应侧的任务。共同通过/共同失败/仅左侧/仅右侧只包含结果已知的 `strict|conditional` pair；未知结果单列。连续指标给双方中位数、配对中位差/比；固定 seed、10,000 次按任务聚类重采样计算差值区间，同一任务 repeat 一起抽取。计算在离线 Worker 中进行，筛选变化后丢弃旧结果；Worker 不可用时保留描述统计并明确区间未计算。

轮次差值要求双方来源与 adapter 一致；输入差值沿用完整覆盖、缓存关系和账本一致条件；完成耗时排除删失或状态未知。每项指标独立给出排除项，不能把总体资格当指标完整性。首页按用户 focus 调整资源与覆盖模块顺序，其他维度始终可访问。结论注明全量测量、已裁决发现、样本机制或假设。

按任务/Trial/模型文本、验证结果、health 筛选后，图表、有效分母、排除项、任务列表和文字结论同步更新。Pair 只在其已有两侧均留在筛选范围时显示，不因过滤而重新匹配 repeat；缺少对应侧仍可单列。全量测量与深读计划/已有发现分开，计划被选中不代表已完成裁决。

根因分类字段为 `finding_type=root_cause` 和 `root_cause_category`。只有 full 且原始全部可分析失败均已有直接证据关联的 confirmed 主因或 indeterminate 裁决时才展示分布；样本机制和假设不能成为已确认主因。无法归因项保留在分母。筛选不能绕过原总体覆盖要求。

各维度按证据选择呈现：coverage 矩阵，F2P/P2P 与 raw/reconciled，资源分布/阶段消耗/请求曲线，生命周期与等待，动作与恢复事件，revision 对齐交付链，故障事实表，完整性候选/裁决表，因果证据链。不要用同一图形压平不同证据语义。

AEO runtime 继续使用现有 JSON 响应，由宿主负责渲染；分析模型不返回 HTML，也不修改 Verifier、Canonical outcome 或人工 Root Cause。此展示层不会改写 AEO prompt 契约。
