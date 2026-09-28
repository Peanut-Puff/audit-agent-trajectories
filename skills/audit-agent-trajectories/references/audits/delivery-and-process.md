# 交付链与过程收敛审计

## 审计问题

Agent 形成的最终状态是否被持久化、验证、捕获并由 verifier 观察；过程是否在错误后收敛到可验收交付。

## 准入条件

至少需要 trajectory 和 patch/artifact 或 verifier。要证明链条完整，还需 mutation 顺序、validation observation、capture hash 和 verifier 对应 candidate。缺失一环时只报告到可证层级。

## 证据来源

- Edit/Write/shell mutation、git status/commit/diff 和文件 hash。
- Validation 命令、完整 stdout/stderr、exit code、scope 和 revision。
- Patch/artifact manifest、capture error、baseline/final commit。
- Final response、Todo、background process、恢复/重试事件。
- Verifier 看到的 patch、revision 和 assertion。

## 状态与指标

对关键交付建立：

`mutation -> persistence -> validation target -> observed result -> capture/hash -> verifier observation`

记录 first/last mutation、last mutation 后 validation、验证范围、重复等价 validation、无新增信息探索、未 join background process、final claim 与证据一致性。

## 审计步骤

1. 确认最终 patch 候选路径和 hash，检查多个 patch 是否矛盾。
2. 反向确定 verifier 实际观察的 artifact/revision。
3. 定位最终 mutation，确认后续 validation 是否针对同一持久化状态。
4. 检查早期测试通过是否被后续 mutation 失效，却仍在 final response 中引用。
5. 检查失败后是否改变假设或方法；依赖/工具恢复后是否重试原始关键动作。
6. 将交付链断裂与代码语义错误分开；前者只有满足首错标准时才成为根因。

## 聚合规则

按 trial 聚合“链条完整/部分/断裂/未知”，另列具体断点。重复 validation 统计 event 数和 trial 数。Completion gate 只在人工确认任务条目、实现、定向断言和观察结果四列闭合后记为完整。

## 禁止推断

- Tool call success 不等于落盘成功。
- 本地测试成功不等于测试了最终 captured patch。
- Patch 存在不等于内容完整、最新或来自正确路径。
- Final response 声称完成不等于 normal completion gate。
- “未在已知命令模式中识别到测试”不等于没有验证。

## 输出与完成检查

每个 finding 记录链条各节点、mutation/validation step、revision/hash、断点、final claim、verifier 后果和证据强度。完成前确认最终 mutation、验证对象和捕获 artifact 是同一个状态，或明确无法证明。
