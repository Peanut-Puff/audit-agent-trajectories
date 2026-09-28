# 安装指南

## 前置条件

- Skill 本体不依赖 Node；确定性提取器需要 Python 3.10+。
- 使用 `npx skills` 时需要可运行 `npx` 的 Node/npm 环境。
- 远程安装前先将本仓库推送到 GitHub 或 `npx skills` 支持的 Git 来源。

以下命令中的 `<source>` 可以是本地仓库绝对路径、GitHub URL，或 `<owner>/audit-agent-trajectories`。

## 使用 npx skills

先检查仓库中可发现的 skill：

```bash
npx skills add <source> --list
```

用户级安装到 Codex 和 Claude Code：

```bash
npx skills add <source> \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --global --yes
```

项目级安装：

```bash
cd /path/to/project
npx skills add <source> \
  --skill audit-agent-trajectories \
  --agent codex claude-code \
  --yes
```

安装到 skills CLI 支持的所有 agent：

```bash
npx skills add <source> \
  --skill audit-agent-trajectories \
  --agent '*' \
  --global --yes
```

默认使用 symlink；需要独立副本时增加 `--copy`。查看和更新：

```bash
npx skills list --global
npx skills update audit-agent-trajectories --global --yes
```

## Codex

推荐直接使用上述 `--agent codex`。Codex 官方也支持用户级 `~/.agents/skills` 和项目级 `.agents/skills`，并会跟随 skill 目录 symlink。

手动用户级安装：

```bash
mkdir -p ~/.agents/skills
ln -s /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories \
  ~/.agents/skills/audit-agent-trajectories
```

项目级安装时，将 symlink 放入项目的 `.agents/skills/`。安装后在 Codex 中使用 `/skills` 查看，或输入 `$audit-agent-trajectories` 显式调用；未出现时重启 Codex。

## Claude Code

推荐使用 `npx skills ... --agent claude-code`。手动用户级目录通常为 `~/.claude/skills`，项目级目录为 `.claude/skills`：

```bash
mkdir -p ~/.claude/skills
ln -s /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories \
  ~/.claude/skills/audit-agent-trajectories
```

`SKILL.md` 只使用标准 `name` 和 `description` frontmatter；`agents/openai.yaml` 是 Codex 可选元数据，其他 agent 可以忽略。

## BitFun

BitFun 可读取标准 Agent Skills，并扫描项目级 `.bitfun/skills`、`.claude/skills`、`.codex/skills`、`.agents/skills` 等目录。因此项目级 npx 安装通常可以直接被 BitFun 发现。

使用 BitFun CLI 独立管理时：

```bash
bitfun skills validate /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories
bitfun skills add /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories --level user
```

安装到当前 BitFun workspace：

```bash
bitfun skills add /absolute/path/to/audit-agent-trajectories/skills/audit-agent-trajectories --level project
```

BitFun 安装命令复制 skill 文件；仓库更新后需要重新导入。若希望持续跟随仓库版本，可将 skill 目录链接到 BitFun 能扫描的 `.agents/skills`、`.claude/skills` 或 `.codex/skills`。

## 其他 Agent

运行 `npx skills --help` 查看当前 CLI 支持的 agent ID，再通过 `--agent <id>` 安装。对于实现 Open Agent Skills 但未列入 CLI 的宿主，将完整的 `skills/audit-agent-trajectories/` 目录复制或链接到它的 skills 根目录。

无论宿主是什么，都必须保留 `SKILL.md`、`references/` 和 `scripts/` 的相对结构；只复制 `SKILL.md` 会破坏方法路由和提取器调用。
