# Harbor、BitFun 与 OpenCode Adapter

## 职责边界

Adapter 只负责输入探测、字段归一化和 provenance，不裁决环境责任、违规、failure mode 或根因。未知格式回退 `harbor-generic`，相关 coverage 降级；不得用默认 0 掩盖缺失。

## 输入探测

- `bitfun`：存在 `agent/bitfun/`，或 trajectory/config agent name 含 `bitfun`。
- `opencode`：trajectory/config agent name 含 `opencode`。
- `harbor-generic`：存在 Harbor 风格 `result.json`，但不符合以上特征。

Job 根目录与 trial 都可能有 `result.json`。存在直接子目录 trial result 时按 job；当前目录有 `agent/` 或 `verifier/` 时优先按 trial。显式 `--mode` 覆盖自动判断。

## 身份与配置

从 result/config/trajectory 提取 trial ID、task name/checksum、agent/runtime、model、environment type、timeout 和资源限制。配置使用 allowlist，禁止序列化未知 kwargs、完整 env 或凭证。

Task checksum 是身份强信号但不是唯一语义证据。Prompt fingerprint 只对可见题面计算；trajectory 没有 user step 时保持 `null`。

## Delivery

按存在性和内容读取 patch 候选：

1. `artifacts/model.patch`
2. `agent/model.patch`
3. `agent/patch/fix.patch`

同时关联 artifact manifest、baseline/final commit、status、stat 和 name-status。多个非空 patch hash 不同则 delivery coverage 为 `contradictory`，不得静默按路径优先级认定最终交付。

## Verifier

关联 `verifier/reward.json`、`result.verifier_result.rewards`、CTRF、XML/report、stdout 和 phase logs。Verifier 指纹使用与 outcome 无关的测试身份集合；没有测试清单时不得使用 reward 值作为指纹。

Recheck/reconciliation 必须关联相同 patch hash 和独立运行 provenance。Raw 与 reconciled 值同时保留。

## Trajectory 与事件

兼容：

- `arguments.command` 与 `arguments.cmd`；
- `bash`、`ExecCommand`、`exec_command` 等 shell tool；
- `write`、`edit`、`multiedit`、`applypatch` 与 shell mutation；
- 字符串、对象或 results 数组 observation；
- 顶层 `subagent_trajectories` 与独立 session/index。

Step timestamp 只用于可证事件间隔。没有 typed start/end 时，不把相邻 step 间隔解释为单个 tool/model duration。

## Token 优先级

- Raw CodeAgent stream 的最后一个 `type=result.modelUsage` 存在时，按模型汇总该累计账本；同级 `usage` 仅是当前 segment。
- BitFun 优先 result `agent_result`，并与 `agent/bitfun/token_usage/model_stats.json` 和 trajectory `final_metrics` 对账。
- OpenCode/通用 Harbor 优先 result `agent_result`，再使用 trajectory `final_metrics`。

`n_cache_tokens`/`total_cached` 默认映射 cache read；只有 schema 明确区分时才填 cache creation。Input 总量不再加 cached tokens。

## Provenance 与安全

每个归一化字段记录 source path/field、adapter、status 和 confidence。命令/observation 写候选前脱敏并限长；报告优先引用原始路径与 step。

Adapter 识别规则变化必须升级 rule/script 版本并用 BitFun、OpenCode、generic 和 unknown fixtures 验证，不得通过扩大正则掩盖 schema 差异。
