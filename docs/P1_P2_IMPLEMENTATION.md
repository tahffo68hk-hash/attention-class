# P1 / P2 技术说明 — Attention is all you need

> 本文档对应 2026-10-14 独立候选工程，源码来自 WorkBuddy `REVIEW_SOURCE.zip` + ChatGPT 的 P0/M1 候选版。用户本地 `E:\Attention is all you need` **未修改**。全部模拟数据；非临床软件。

## P1. 多患者联合优化

- 入口：`POST /api/v1/optimization/preview`，请求：`{"admission_request_ids":[1,2,3],"solver":"auto"}`。
- 鉴权：仅 `ADMIN` / `NURSE`。只读计算，不创建或变更 `bed_allocations` / `beds`。
- 只接受真实存在且处于 `PRE_ADMITTED`、已预登记、没有活动分配的住院证；不容许重复 ID。
- **候选来源**：直接复用现有 `recommend_beds()`；它先用 H1–H4 硬约束过滤，再返回五维原有评分。不能绕过隔离策略，也不会自行更改其公式。
- 安全上限：每批 ≤30 个申请、≤100 张不同床位、≤2000 条匹配边，单一申请候选 ≤100；超过则拒绝。
- 两种对照：`greedy`（先优先级再住院证 ID；床位按最高分）与 `exact_min_cost_flow`（整数最小费用流）；安装可选 OR-Tools 后 `auto` 可选 `ortools_cp_sat`，只接受已证明 `OPTIMAL` 的结果，超时/未安装回退到精确流法。显式 `cp_sat` 请求若不能证明最优则报错。

### 目标函数（先后顺序，严格字典序）

1. **最大化被成功安排的人数**。例如 2 名轻症成功安排优于仅 1 名危重成功安排，这是算法的教学假设，**不属于医疗收治政策**。
2. 人数相同时，最大化已匹配患者的**五级优先级权重和**（危重=5、重症=4、急症=3、普通=2、轻症=1）。
3. 仍相同时，最大化已有五维推荐评分（先放大 100 倍转整数）；最后由固定的申请 / 床位编号次序打破平局。

算法通过足够大的整数权重保证第一目标优先于后两个，第二目标优先于后一个。每个申请最多匹配一张床；每张床最多分给一个申请。`optimize()` 会返回匹配列表、未匹配申请、优先级和、评分和、耗时、是否证明最优。

**重要**：此时得到的是冻结快照上的计划，不是并发安全的床位分配动作。真正确认仍需调用已有 `POST /allocations`（每人一次、幂等键、数据库事务内重验）；不提供自动批量写入，避免对 M1 数据一致性修复形成旁路。

### 可复现实验

```bash
PYTHONPATH=backend python scripts/benchmark_optimization.py --seed 20261014 --output docs/p1_benchmark_synthetic.csv
```

CSV 来自固定种子的虚构候选矩阵，`runtime_ms` 是当前 CPU 环境的算法计算时间，不含 SQL、网络和前端。数据不构成临床效果或真实医院吞吐量的证明。最小费用流已通过 75 组随机小样本与穷举比较目标三元组（安排人数、优先级和、评分和）。

## P2. 辅助解释与模型接入

### 规则版（默认）

- `POST /api/v1/assistant/explain`：`{"admission_request_id":1,"bed_id":3,"mode":"rules"}`。
- `POST /api/v1/assistant/explain-plan`：`{"admission_request_ids":[1,2],"solver":"auto"}`。
- 两者都使用当前真实后端的推荐结果 / 联合优化结果，不篡改硬约束、得分或实际床位分配。
- 返回明确标识 `provider=deterministic_rules`、`real_ai=false`、`performed_allocation=false`，**不得宣传为大模型生成**。

### 真实模型适配（代码已实现，但默认关闭）

- 仍走 `/assistant/explain`，使用 `mode=llm` 且 `confirm_external_call=true`。
- 服务端还必须显式配置 `ASSISTANT_EXTERNAL_ENABLED=true`、`ASSISTANT_API_KEY`、`ASSISTANT_MODEL` 与 HTTPS 端点；默认值 false，没有安装/配置即可拒绝调用。
- 外发内容**仅包括**患者优先级序号、是否隔离、床型、最终分数、五维原始分与贡献分、警示数量；**不发送**姓名、住院证号、床号、诊断、患者联系信息、任意自由文本。
- 使用 OpenAI-compatible Chat Completions JSON 响应协议；响应长度和字段形状有校验，失败返回受控错误。
- 返回 `real_ai=true`、`review_required=true`、`AI_DRAFT_REVIEW_REQUIRED`；真实费用不可验证时 `cost_usd=null`，而非假造费用零。
- 外部模型不会自动调整推荐、绕过约束或执行分配。无背景任务，只有操作者点击时触发。真实调用的 provider/model/promptVersion/token/latency 会写审计日志，不存储完整提示和个人信息。
- **当前用户未授权本次付费调用，且本轮没有发生任何真实模型请求**。未来真实调用必须再次明确授权和设置预算，建议在接入时加入预算强制门禁。

## 前端

新增 `OptimizationView.vue` 与 `AssistantView.vue`，已加入侧边栏和路由，中文文案明确标示教学/非临床/模拟或 AI。全局排床页面支持选择最多30人、比较两方案、查看指标、逐人跳到既有推荐页人工确认；辅助解释页可选住院申请和真实候选床位，显示结构化证据与人工复核提示。

**注意**：原 WorkBuddy 浏览器验收前端源码未包含在最早的 `REVIEW_SOURCE.zip`，这里的两个页面只在 ChatGPT 上一轮的独立 Vue 候选版本上开发；整合到 Windows 本地时应优先保留 WorkBuddy 已验收页面，择优合入新增两个页面。
