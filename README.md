# Audit Agent Trajectories

面向 Harbor、DeepSWE、Pier 及类似 coding-agent evaluation 的证据化轨迹审计 skill。它先判断数据的可分析性与可比性，再分别审计环境、评测完整性、Token、耗时、得分、交付链、失败模式和首个 consequential break。

当前版本：`v2.6.0`。

## 安装

本地仓库安装到 Codex 和 Claude Code：

```bash
npx skills add /absolute/path/to/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --global --yes
```

仓库发布到 GitHub 后，将本地路径替换为 `<owner>/audit-agent-trajectories`：

```bash
npx skills add <owner>/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --global --yes
```

安装到当前项目时去掉 `--global`。安装到 `npx skills` 支持的所有 agent 时使用 `--agent '*'`，但显式列出实际使用的 agent 更容易审计安装范围。

BitFun 可直接导入 skill 目录：

```bash
bitfun skills validate /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories
bitfun skills add /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories --level user
```

完整的 Codex、Claude Code、BitFun、项目级和手动安装方法见 [安装指南](docs/installation.md)，兼容性和目录映射见 [兼容性说明](docs/compatibility.md)。

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
  --focus all
```

运行时只依赖 Python 3.10+ 标准库。

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
npx skills add . --list
```

版本策略和发布流程见 [版本管理](docs/versioning.md)。

## 规范基础

Skill 格式遵循 [Open Agent Skills](https://agentskills.io/specification)；Codex 的加载目录和使用方式以 [OpenAI 官方 Build skills 文档](https://learn.chatgpt.com/docs/build-skills) 为准；`npx skills` 安装能力来自 [skills CLI](https://github.com/vercel-labs/skills)。
