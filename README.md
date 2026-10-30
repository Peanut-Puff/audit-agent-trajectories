# Audit Agent Trajectories

面向 Harbor、DeepSWE、Pier 及类似 coding-agent evaluation 的证据化轨迹审计 skill。它先判断数据的可分析性与可比性，再分别审计环境、评测完整性、Token、耗时、得分、交付链、失败模式和首个 consequential break。

当前版本：`v2.9.0`。

## 安装与更新

全局安装到 Codex 和 Claude Code：

```bash
npx skills add Peanut-Puff/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --global --yes
```

更新全局安装：

```bash
npx skills update audit-agent-trajectories --global --yes
```

项目级安装与更新：

```bash
cd /path/to/project
npx skills add Peanut-Puff/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --yes
npx skills update audit-agent-trajectories --project --yes
```

查看已安装的全局 skill：

```bash
npx skills list --global
```

完整的 npx 安装说明见 [安装指南](docs/installation.md)，兼容性见 [兼容性说明](docs/compatibility.md)。

## 使用

Codex 中可显式调用：

```text
$audit-agent-trajectories 审计 /path/to/job，重点分析环境、Token、耗时和失败根因。
```

也可以让支持 Agent Skills 的宿主根据 `description` 自动选择该 skill。默认模式是全量测量加确定性样本深读；只有 `full` 覆盖全部可分析失败后，才能报告全量根因分布。

确定性提取器：

```bash
python3 skills/audit-agent-trajectories/scripts/audit_trajectories.py \
  /path/to/job \
  --output /path/to/audit-output \
  --mode auto \
  --depth standard \
  --focus all \
  --output-layout compact
```

运行时只依赖 Python 3.10+ 标准库。

需要跨 BitFun/OpenCode/Harbor 对齐 model round 和 tool call 时，先生成紧凑事件账本；它同时接受规范化目录、解压后的 AEO case-log 和原始 case-log ZIP：

```bash
python3 skills/audit-agent-trajectories/scripts/normalize_trajectory_events.py \
  /path/to/job-or-case-logs.zip \
  --output /path/to/normalized-events

python3 skills/audit-agent-trajectories/scripts/classify_round_actions.py \
  /path/to/normalized-events --output /path/to/round-actions

python3 skills/audit-agent-trajectories/scripts/classify_round_stages.py \
  /path/to/normalized-events --output /path/to/round-stages
```

主审计的 compact 布局只生成 `report.md`、`audit.json` 和 `findings.jsonl`；旧多文件目录使用 `--output-layout expanded`。轮次归一化默认生成 `summary.json` 和一个 `trajectory-events.jsonl` 事件包，动作/stage 分类各生成一个 JSON；逐轮分类使用 `--include-rounds`。

Trial 或 Job 均可显式加 `--html` 附加离线 `report.html`。Job 同时生成 `report-details/`，提供筛选总览、分布、覆盖矩阵和 Trial/配对静态详情。也可从已有审计独立渲染一份审计或两份 Trial/Job 审计，按需接入归一化请求曲线与人工语义阶段：

```bash
python3 skills/audit-agent-trajectories/scripts/render_audit_html.py \
  /path/to/left-audit /path/to/right-audit \
  --normalized /path/to/normalized-events \
  --annotations /path/to/presentation.json \
  --output /path/to/pair-report.html
```

HTML 保留健康、verifier、交付链、裁决与证据入口，不覆盖人工 findings 或 Markdown。筛选同步更新图表、分母和结论范围；分享 Job 报告时须一起保留同名详情目录。支持范围与标注契约见 [HTML 展示层](skills/audit-agent-trajectories/references/html-presentation.md)。

AEO 可通过版本化 `AnalysisAgentAdapter` 把裁剪、脱敏的 Trial facts 与 addressable
evidence 交给该方法。此模式不要求把 AEO Trace ZIP 改造成 Harbor 目录，也不允许分析
结果覆盖 Verifier、Canonical outcome 或人工 Root Cause；契约见
[`references/adapters/aeo.md`](skills/audit-agent-trajectories/references/adapters/aeo.md)。

## 仓库结构

```text
skills/audit-agent-trajectories/  # 可安装 skill 包
docs/                             # 安装、兼容和版本说明
scripts/validate_package.py       # 仓库级一致性校验
.github/workflows/validate.yml    # CI
VERSION                           # 仓库发行版本
CHANGELOG.md                      # 版本变更
```

Skill 内部采用渐进披露：`SKILL.md` 只负责流程和文档路由，具体方法位于 `references/`，确定性抽取和测试位于 `scripts/`。

## 验证

```bash
python3 scripts/validate_package.py
python3 skills/audit-agent-trajectories/scripts/test_audit_trajectories.py -v
python3 skills/audit-agent-trajectories/scripts/test_normalize_trajectory_events.py -v
python3 skills/audit-agent-trajectories/scripts/test_classify_round_actions.py -v
python3 skills/audit-agent-trajectories/scripts/test_classify_round_stages.py -v
python3 skills/audit-agent-trajectories/scripts/test_render_audit_html.py -v
node skills/audit-agent-trajectories/scripts/test_job_statistics.cjs
npx skills add . --list
```

版本策略和发布流程见 [版本管理](docs/versioning.md)。

## 规范基础

Skill 格式遵循 [Open Agent Skills](https://agentskills.io/specification)；Codex 的加载目录和使用方式以 [OpenAI 官方 Build skills 文档](https://learn.chatgpt.com/docs/build-skills) 为准；`npx skills` 安装能力来自 [skills CLI](https://github.com/vercel-labs/skills)。
