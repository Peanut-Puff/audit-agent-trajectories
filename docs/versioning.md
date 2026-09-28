# 版本管理

## 版本来源

- `VERSION`：仓库发行版本，也是 Git tag 的版本。
- `METHODOLOGY_VERSION`：分析方法语义版本，写入 manifest 和 candidate。
- `RULE_VERSION`：adapter、候选识别和确定性选择规则版本。
- `SCHEMA_VERSION`：机器输出的破坏性 schema 版本。
- `SCRIPT_VERSION`：提取器实现版本。

首个独立仓库版本为 `v2.0.0`，对应方法版本 `2.0.0`。

## Semantic Versioning

- **MAJOR**：改变 health/比较/违规/根因语义，删除或重命名 CLI/机器字段，或使旧报告无法按原方法解释。
- **MINOR**：新增专项审计、adapter、可选字段、候选规则或兼容宿主，且旧调用仍有效。
- **PATCH**：修正文档、误报、解析 bug、脱敏或测试，不改变已有字段的公开语义。

仓库版本与方法版本通常同步。纯安装文档或 CI 修复可以只提升仓库 PATCH；方法语义变化必须同步提升 `METHODOLOGY_VERSION`。

## 发布流程

1. 更新实现和文档，确保 `SKILL.md` 路由覆盖新增 reference。
2. 按变化类型更新 `VERSION`、脚本版本常量和 `CHANGELOG.md`。
3. 运行：

   ```bash
   python3 scripts/validate_package.py
   python3 skills/audit-agent-trajectories/scripts/test_audit_trajectories.py -v
   npx skills add . --list
   ```

4. 检查上游远程；已有远程时先 fetch/rebase，解决冲突后重跑校验。
5. 提交 `release: vX.Y.Z`，创建 annotated tag：

   ```bash
   git tag -a vX.Y.Z -m "audit-agent-trajectories vX.Y.Z"
   ```

6. 推送 branch 和 tag。远程仓库的可见性、owner 和许可证必须由维护者明确选择。

## 兼容性承诺

- CLI 参数或生成目录发生破坏性变化时提升 MAJOR。
- Additive JSON 字段不提升 `SCHEMA_VERSION`；删除、改名或改变字段语义才提升。
- Candidate 规则改变时提升 `RULE_VERSION`，即使机器 schema 不变。
- 报告必须记录所有版本，使旧分析可以按当时方法复核。
