# Token 与成本审计

## 审计问题

每个 trial 消耗了哪些可比的模型资源，记录是否完整，资源差异与结果之间能说明什么，不能说明什么。

## 准入条件

至少需要一个明确口径的累计 usage ledger。只有 per-step 零值或单 segment usage 时 coverage 为 `partial`；不同 adapter 字段语义不明时只作描述性比较。

## 证据来源

- `result.agent_result`、trajectory `final_metrics`。
- `result.step_results[].agent_result`，与顶层 agent result 按 execution context 汇总。
- 最后一个 raw-stream `type=result` 的累计 `modelUsage`。
- BitFun `token_usage/model_stats.json` 和 provider 账单/成本字段。
- Model、session、request、segment 和 subagent 关系。

## 指标

分开记录 `input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_creation_tokens`、request、session、model 和 cost。只有来源明确提供时才填值；缺失保持 `null`。

`total_tokens_excluding_cache = input + output`。Cached input 通常已包含在 input/prompt 中，不再次相加。没有价格表或 provider 账单时不推算 cost。

## 审计步骤

1. 识别 adapter 的权威累计 ledger 和次级交叉验证来源。
2. 汇总顶层与 step result 的 agent result；用 `aeo_model_usage` 核对 request/coveredRequest 和 input/output/collection completeness。
3. 没有 completed-request 证据的全零 usage 保持 missing；schema 明确声明零请求且有 excluded request 时才保留确认零值。
4. 检查 cumulative 与 segment 语义，禁止累加已经累计的 result。
5. 按 model/session 核对总量、请求数和 cache 口径。
6. 对差异记录原值和 provenance，不静默选择。
7. 计算完整率、总量、中位数、P90、成功/失败分布和同任务配对差。
8. 将全量资源消耗与成功条件下效率分开，避免 survivorship bias。

CodeAgent 多 segment 存在累计 `modelUsage` 时，使用最后一个 result 并按模型汇总；同级 `usage` 只是当前 segment，不是累计总量。

## 聚合规则

每个指标逐项排除缺失并报告有效/缺失数。跨 adapter 只有字段语义、缓存包含关系和范围一致时才合并。配对比较按 task pair 重采样，不按 request 重采样。

## 禁止推断

- 缺失 token 不计为 0。
- Cache token 不重复加入 input。
- 高 token 与失败相关，不证明 token 被“浪费”或模型能力不足。
- 不把总 token 差异当成单一 agent/model 因果效应；任务、上下文、工具和 runtime 都是混杂因素。
- 不从 token 数反推准确 cost，除非有匹配的价格与计费语义。

## 输出与完成检查

输出每个 token 字段的值、单位、范围、来源、完整度和比较资格；聚合报告包含完整率、分布、配对 n 和口径限制。确认 cache 未重复、segment 未重复累计、缺失未转 0。
