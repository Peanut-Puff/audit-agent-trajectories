# 安装指南

## 前置条件

- Skill 本体不依赖 Node；确定性提取器需要 Python 3.10+。
- 使用 `npx skills` 时需要可运行 `npx` 的 Node/npm 环境。

## 使用 npx skills

先检查仓库中可发现的 skill：

```bash
npx skills add Peanut-Puff/audit-agent-trajectories --list
```

用户级安装到 Codex 和 Claude Code：

```bash
npx skills add Peanut-Puff/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --global --yes
```

项目级安装：

```bash
cd /path/to/project
npx skills add Peanut-Puff/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --yes
```

安装到 skills CLI 支持的所有 agent：

```bash
npx skills add Peanut-Puff/audit-agent-trajectories \
  --skill audit-agent-trajectories \
  --agent '*' \
  --global --yes
```

查看已安装的全局 skill：

```bash
npx skills list --global
```

更新全局安装：

```bash
npx skills update audit-agent-trajectories --global --yes
```

更新项目级安装：

```bash
npx skills update audit-agent-trajectories --project --yes
```

安装或更新后，在 Codex 中使用 `/skills` 查看，或输入 `$audit-agent-trajectories` 显式调用；宿主尚未刷新时重启对应客户端。
