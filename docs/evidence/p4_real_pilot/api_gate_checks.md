# P4 Real Pilot — API 级门禁与副作用核验（原始观测）

采集时间：2026-10-14 13:43（GMT+8）
后端：`http://127.0.0.1:8000`（uvicorn，本地隔离实例）
账号：演示 ADMIN（`admin`）；口令在运行时从项目 `backend/seed.py` 解析，未落字面量。
数据库：隔离 MySQL 8.0.32 @ `127.0.0.1:3307`，库 `hospital`（演示库）。

> 本文件只记录**响应元数据**。所有请求/响应中均不含密钥、Authorization 头或原始患者身份数据。

## 1. DeepSeek 配置状态

```
GET /api/v1/assistant/provider-status   → 200
{"provider":"deepseek","model":"deepseek-flash","enabled":false,
 "real_call_requires_confirmation":true,"default_mode":"rules","no_live_call":true}

响应体是否包含 key/secret 字段：否
```

## 2. 规则解释（默认路径，不得外发）

```
POST /api/v1/assistant/explain  {mode:"rules"}   → 200
provider=deterministic_rules  real_ai=false  externally_sent=false
status=RULES_ONLY  cost_estimate_cny=null  latency_ms=null
解释文本非空：是      五维评分项数量：5
```

## 3. 真实 AI 路径门禁（服务端未启用时必须拒绝，且不得产生任何模型结果）

```
POST /api/v1/assistant/explain  {mode:"llm", confirm_external_call:true}  → 403
{"code":"PERMISSION_DENIED","message":"DeepSeek 未启用或密钥未配置", ...}

POST /api/v1/assistant/explain  {mode:"llm"}（未确认）                     → 403
{"code":"PERMISSION_DENIED","message":"调用真实模型前必须单独确认外部调用", ...}
```

## 4. 整批方案解释

```
POST /api/v1/assistant/explain-plan  {mode:"rules"}                       → 200
provider=deterministic_rules  real_ai=false  assigned_count=3  baseline_assigned_count=3

POST /api/v1/assistant/explain-plan  {mode:"llm", confirm_external_call:true}  → 403
{"code":"PERMISSION_DENIED","message":"DeepSeek 未启用或密钥未配置", ...}
```

## 5. 业务副作用核验（调用前后快照）

| 表 | 调用前 | 调用后 | 结论 |
|---|---|---|---|
| `beds` | 44 | 44 | 未变 |
| `bed_allocations` | 15 | 15 | 未变 |
| `admission_requests` | 22 | 22 | 未变 |
| `bed_status_logs` | 34 | 34 | 未变 |
| 活动占用（RESERVED/ADMITTED） | 5 | 5 | 未变 |
| `audit_logs` | 134 | 138 | **+4（设计内留痕，见下）** |

床位状态分布前后一致：
`{AVAILABLE:37, RESERVED:2, OCCUPIED:3, CLEANING:1, MAINTENANCE:1}`

**`audit_logs` +4 的逐条来源**（全部为设计内行为，非分配写入）：

| id | action | result | 说明 |
|---|---|---|---|
| 135 | `LOGIN` | SUCCESS | 本次核验的 ADMIN 登录 |
| 136 | `RECOMMEND` | SUCCESS | 定位虚构目标时的推荐查询（只读） |
| 137 | `AI_EXPLANATION_REQUEST` | FAILURE | llm+confirm 被拒；明细含 `no_prompt_logged:true` |
| 138 | `AI_PLAN_EXPLANATION_REQUEST` | FAILURE | llm+confirm 被拒；明细含 `no_request_ids_logged:true` |

137/138 证明：**被拒绝的真实 AI 尝试同样留痕，且明细明确记录未记录任何提示词/住院证编号**。

## 6. 结论

- 规则解释功能正常可用（single + plan 均 200）。
- 无授权时真实 AI 路径 100% 拒绝，未产生任何虚假 AI 结果。
- 无任何床位分配副作用；历史记录未变动。
