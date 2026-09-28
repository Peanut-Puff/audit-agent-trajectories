# 兼容性说明

## 支持矩阵

| 宿主 | npx skills agent ID | 项目级目录 | 用户级目录/方式 | 状态 |
| --- | --- | --- | --- | --- |
| Codex | `codex` | `.agents/skills` | `npx` 管理；官方目录 `~/.agents/skills` | 已验证发现与安装 |
| Claude Code | `claude-code` | `.claude/skills` | `~/.claude/skills` | 已验证发现与安装 |
| BitFun | 无专用 ID | `.bitfun/skills`，并扫描多个通用目录 | `bitfun skills add --level user` | 按源码命令与 registry 验证 |
| Cursor 等 | 运行 `npx skills --help` 查询 | 由 skills CLI 映射 | 由 skills CLI 映射 | 标准格式兼容 |

## 格式兼容

- `SKILL.md` frontmatter 只要求 `name` 和 `description`，符合 Open Agent Skills。
- `references/` 使用相对 Markdown 链接，并由入口直接路由到所有方法文档。
- `scripts/` 使用 Python 3.10+ 标准库，不依赖 Codex 专有工具。
- `agents/openai.yaml` 只增强 Codex/ChatGPT UI；Claude Code、BitFun 和其他宿主可以忽略。
- 输入与输出路径由调用者提供，不依赖特定 agent 的工作区变量。

## 已验证场景

- `npx skills add <local-repo> --list` 能发现 `audit-agent-trajectories`。
- Codex 和 Claude Code 的隔离项目安装会保留完整 skill 目录。
- BitFun 的 skill parser 接受同一 `SKILL.md`，其 registry 扫描 `.bitfun/.claude/.codex/.agents` 等项目目录。
- 单 trial、单 job 和配对 job 的 extractor 测试不依赖宿主。

## 宿主差异

- 显式调用语法由宿主决定；Codex 使用 `$audit-agent-trajectories` 或 `/skills`。
- 安装器可能选择 symlink 或 copy。Copy 安装不会自动跟随 Git 更新。
- BitFun 的专用 CLI 是复制安装；通用目录 symlink 更适合本地开发。
- 宿主是否自动调用 skill 取决于其 discovery 和 description 匹配策略，不影响显式调用。

## 安全边界

安装 skill 等同于安装可被 agent 读取并执行的提示与脚本。安装前审查 `SKILL.md` 和 `scripts/`；生产环境继续由宿主权限、sandbox 和网络策略约束，skill 本身不授予额外权限。
