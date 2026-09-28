# 环境与基础设施审计

## 审计问题

环境是否阻止 trial 形成可评价行为，故障发生在哪个域和阶段，agent 的恢复决策是否共同影响结果。

## 准入条件

至少需要 result/exception、trial 或 worker 日志、trajectory 终止位置之一。只有异常字符串而没有上下文时，environment coverage 为 `partial`；无法区分 agent 命令错误和平台故障时保持 `unknown`。

## 证据来源

- Provider 响应、rate limit、请求超时和 adapter 日志。
- Worker、容器、镜像、mount、磁盘、资源限制、网络/DNS/代理日志。
- 依赖解析、工具安装、关键命令 stderr/exit code。
- Verifier setup、runner 和 phase logs。
- Agent 对故障的识别、恢复、重试和最终 evaluator-visible state。

## 状态

- `infra_only`：没有形成可评价行为，且直接基础设施证据闭环。
- `agent_only`：环境可用，首个关键失败来自 agent 可控决策。
- `mixed_contribution`：环境事件与 agent 的恢复、验证或提交策略共同决定结果。
- `unknown`：现有证据无法分离责任。

故障域使用 `provider|worker|network|container|storage|dependency|tooling|verifier|unknown`，并记录发生阶段。

## 审计步骤

1. 从 exception/termination 反向定位最后一个可见事件和 evaluator 可见产物。
2. 读取完整 stderr、exit code 和上下游日志，排除管道或后续命令掩盖状态。
3. 检查同 worker、时间窗、provider、镜像或任务族是否聚集。
4. 确认 agent 是否识别故障、改变方法、重试原始关键动作并复核结果。
5. 分别写基础设施事件、agent 可控决策和二者的因果边界。
6. 如建议重跑，声明相同 patch、verifier、环境、预算和成功判据。

## 聚合规则

按 trial 计数，不把同一 trial 的多条日志重复计为发生次数。故障域和责任状态分别聚合；`unknown` 不并入基础设施责任率。跨 job 比较还需相同 timeout、网络和资源口径。

## 禁止推断

- Timeout 是终止事件，不自动是根因。
- Exit 137 只证明 `SIGKILL`；没有 kernel、cgroup 或 runtime 证据不得写 OOM。
- 单次 connection error 不证明系统性网络故障。
- Provider/tool 错误出现过，不代表它决定了最终失败。
- Post-run verifier 不向 agent 返回修复反馈是正常评测流程。

## 输出与完成检查

每项 finding 记录 trial、故障域、阶段、责任状态、直接证据、agent 恢复行为、最终可见状态、重跑条件和置信度。完成前确认基础设施事实和行为根因没有混成一个标签。
