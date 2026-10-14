# P4 DeepSeek Real Provider Pilot — 真实调用验收报告

```
REAL_DEEPSEEK_PILOT = BLOCKED
```

- **Pilot ID**：`P4PILOT-20261014T140727+0800`（持久化于 `.workbuddy/p4_pilot_state.json`，随运行器首次运行生成一次）
- **执行时间**：2026-10-14 13:42 – 14:10（GMT+8）
- **基线 HEAD（执行前）**：`b3c2a97`
- **真实 DeepSeek Chat Completions 请求数**：**0 / 授权 2**
- **实际计费**：**¥0**（未发起任何请求）
- **本地估算费用**：**¥0**（无调用）；两次调用的**最坏情况建模上限 ¥0.012286**（随演示库快照变化，见 §4.2 注）

---

## 1. 结论与阻塞原因

本次 Pilot **未能执行真实调用**，判定为 **BLOCKED**，原因单一且明确：

> **本机未配置 DeepSeek API Key。** `DEEPSEEK_API_KEY` 在 OS 环境变量层与
> `backend/.env`（已 gitignore）中**均为空**，`deepseek_provider.is_ready()` 返回 `False`。

按本次授权要求第 2 条：「如果本地尚未配置密钥，**停止并要求用户自行在本机填入；
不得向用户索取明文密钥**」。据此：

- 未向用户索取任何明文密钥；
- 未将任何密钥写入代码、日志、终端回显或 Git；
- **未发起任何真实 DeepSeek API 请求**（真实请求数 = 0，费用 = ¥0）；
- 其余所有可离线执行的准备与收尾核验均已完成（见下文）。

---

## 2. 调用前检查（已完成）

| 检查项 | 结果 |
|---|---|
| 仓库状态 | HEAD `b3c2a97`，工作区干净 |
| P4 交付物在库 | `backend/app/services/deepseek_provider.py`、`backend/tests_p4/`、`docs/p4/` 均已跟踪 |
| 密钥来源 | 仅 `backend/.env`（gitignore 规则 `.gitignore:16`）与服务端环境变量；**两者均无取值** |
| `.env` 是否被跟踪 | **否**（未被 Git 跟踪，密钥不会入库） |
| Provider endpoint | `https://api.deepseek.com/chat/completions`（代码内固定常量，不接受客户端传入） |
| Provider model | `deepseek-flash` |
| 请求参数 | `thinking={"type":"disabled"}`、`response_format={"type":"json_object"}`、`max_tokens=500`、`stream=false` |
| JSON 强制输出 | 系统提示明确要求「生成纯 JSON 对象 `{"explanation":...,"cautions":[...]}`」；`response_format=json_object` 双重保证 |
| 自动重试 | **无**。`httpx.Client(...)` 未装配 RetryTransport，一次点击至多一次外发 |
| 外部调用开关 | 全程 `DEEPSEEK_EXTERNAL_ENABLED=false`（**从未启用**） |

### 2.1 计费口径（DeepSeek 官方实时价目）

来源：`https://api-docs.deepseek.com/zh-cn/quick_start/pricing`（抓取于 2026-10-14）。
高峰时段 = 北京时间周一至周五（不含法定节假日）**9:00–12:00、14:00–18:00**；其余为空闲时段。

本次采用**高峰 + 输入全部缓存未命中**的保守口径（模型 `deepseek-flash`）：

| 项目 | 空闲时段（元/百万 tokens） | **本次采用：高峰（元/百万 tokens）** |
|---|---|---|
| 输入（缓存命中） | 0.02 | **0.04** |
| 输入（缓存未命中） | 1 | **2** |
| 输出 | 4 | **8** |

> 兜底口径：即便误按 `deepseek-v4-pro` 高峰费率（未命中 9 元 / 输出 27 元）计价，
> 结论亦不变（见 §4 预算）。**估算非实际账单**，本次实际扣费为 ¥0。

---

## 3. Pilot 运行 ID 与持久计数（已建立）

- 运行器：`scripts/p4_real_pilot.py`
- 持久状态：`<repo>/.workbuddy/p4_pilot_state.json`（`.workbuddy/` 已 gitignore，**不入库**）
- 约束：授权上限 2 次、预算 ¥0.50；**发起网络请求前先占用额度并落盘**，
  因此崩溃 / 超时 / 重启 / 重复点击均会消耗额度，无法突破上限。
- 当前状态：

```json
{
  "pilot_id": "P4PILOT-20261014T140727+0800",
  "authorized_max_requests": 2,
  "authorized_budget_cny": 0.5,
  "attempts": [],
  "cumulative_estimate_cny": 0.0
}
```

> **修复记录（本轮）**：`load_state()` 原实现只在内存中生成 Pilot ID、**不落盘**，
> 会导致每次运行生成新 ID（持久运行 ID 失效）。已改为**首次调用即 `save_state()` 落盘**，
> 并经跨进程复读验证：连续两次 `--status` 返回同一 `pilot_id`。
> 注：状态文件位于 gitignore 的 `.workbuddy/`，**每台机器独立**，不入库。

`--execute` 闸门实测（无密钥时）：

```
[BLOCKED] DeepSeek 未就绪：需要服务端密钥且 DEEPSEEK_EXTERNAL_ENABLED=true。
          本脚本不会向用户索取明文密钥；请自行在 backend/.env 填入后重启后端。
EXIT=2      ← 未消耗任何额度、未发起任何网络请求
```

---

## 4. 离线预检：出站载荷与预算（零网络，已完成）

为在不产生任何费用的前提下核验「最终外发 JSON」，彩排使用
`httpx.MockTransport` 驱动**真实 Provider 代码**（`deepseek_provider.generate`），
拦截全部网络流量。彩排结论：**24/24 项检查全部 PASS，真实网络请求 = 0**。
完整输出见 `docs/evidence/p4_real_pilot/dry_run_console.txt`（修复后重跑，24 项检查仍全 PASS）。

### 4.1 出站请求核验（两条路径一致）

| 检查 | 结果 |
|---|---|
| endpoint 固定为 `api.deepseek.com/chat/completions` | PASS |
| `model == deepseek-flash` | PASS |
| `thinking == {"type":"disabled"}` | PASS |
| `response_format == {"type":"json_object"}` | PASS |
| `stream == false` | PASS |
| `max_tokens <= 500` | PASS |
| 完整 messages JSON ≤ 8 KB | PASS（single 1167 B / plan 976 B） |
| 系统提示要求输出 JSON | PASS |
| 用户消息 == 白名单快照（逐字节相等） | PASS |
| 白名单不含任何识别性信息 | PASS |
| Authorization 头存在且落盘前已 `<REDACTED>` | PASS |

### 4.2 真实外发载荷（脱敏快照，SHA256 备案）

**single（单床解释，功能类型 = single）**

```json
{"kind":"bed_explanation","teaching_only":true,"priority_rank":2,"requires_isolation":false,
 "bed_type":"NORMAL","final_score":79.24,"warning_count":0,
 "score_dimensions":[{"key":"distance","raw_score":75.74,"contribution":24.2381},
 {"key":"priority_fit","raw_score":100.0,"contribution":28.0},
 {"key":"ward_balance","raw_score":50.0,"contribution":9.0},
 {"key":"cost","raw_score":100.0,"contribution":12.0},
 {"key":"preference","raw_score":60.0,"contribution":6.0}]}
```
SHA256：`9e27e6db1f111ae700ac0156a79da784066251ea7885c8cc327f09b35b00527f`

**plan（整批解释，功能类型 = plan）**

```json
{"kind":"aggregate_bed_allocation_preview","teaching_only":true,"request_count":2,
 "candidate_edges":7,"admitted_gain":0,
 "greedy":{"admitted":2,"priority_sum":4,"score_sum":161.29},
 "optimized":{"admitted":2,"priority_sum":4,"score_sum":161.29,
 "method":"exact_min_cost_flow","proven_optimal":true}}
```
SHA256：`ffd3ef45cf8bfd2c954c3eb09834798671373088ad6dcb0bd0be4577e3bb30d4`

> **注（载荷随演示库快照变化）**：上述载荷取自项目内**虚构演示库的实时快照**
> （`recommend_beds()` 的当前候选与 `optimization_preview.preview(solver="auto")` 的当前结果）。
> 演示库在本会话期间正被操作者通过前端正常使用（审计可见 admin@127.0.0.1 的
> RECOMMEND/RESERVE_BED/UPDATE 记录），因此 `final_score`、候选数、字节数与 SHA256
> 会随数据变化。**不随数据变化的**是本次要核验的不变量：白名单结构、
> 唯一 endpoint/模型/参数、无识别性字段、以及预算上界口径（§4.3）。
> 如需固定复现，请先冻结演示库快照再执行 `--dry-run`。

**白名单核验**：两条载荷均已通过 `_safe_evidence` fail-closed 白名单，
断言结果 = 无禁止键名（`patient_id`/`admission_request_id`/`bed_id`/`bed_code`/
`certificate_no`/`patient_name`/`diagnosis` 等）、无识别性取值（姓名、住院证号、床号）。
两路数据分别来自**真实项目的 `recommend_beds()` 五维评分**与
**`optimization_preview.preview(solver="auto")` 的贪心/精确优化结果**，均为虚构演示数据。

### 4.3 预算闸门

| 路径 | 输入上界（1 token/字节） | 输出上界 | 最坏情况（flash 高峰） | 兜底（pro 高峰） |
|---|---|---|---|---|
| single | 1167 tokens | 500 | ¥0.006334 | ¥0.024003 |
| plan | 976 tokens | 500 | ¥0.005952 | ¥0.022284 |
| **合计** | — | — | **¥0.012286** | **¥0.046287** |

两次调用最坏情况合计 ¥0.012286（兜底口径 ¥0.046287）**均远低于 ¥0.50 授权预算**。
结论：预算充足，不存在因费用不可估算或可能超限而必须放弃的情形 ——
本次阻塞**只**来自缺少 API Key。

---

## 5. 真实调用记录

授权允许 **2 次**，实际发生 **0 次**。

| 字段 | 调用 #1（single） | 调用 #2（plan） |
|---|---|---|
| Pilot ID | `P4PILOT-20261014T140727+0800` | 同左 |
| 时间 | —（未执行） | —（未执行） |
| Endpoint / 模型 | `api.deepseek.com/chat/completions` / `deepseek-flash` | 同左 |
| 功能类型 | single | plan |
| 外发白名单检查 | **通过（离线彩排已验）** | **通过（离线彩排已验）** |
| 脱敏载荷 SHA256 | `9e27e6db…527f` | `ffd3ef45…30d4` |
| HTTP 状态码 | **未发起** | **未发起** |
| DeepSeek request ID | 未发起（且现有 API 契约未透出 `id` 字段） | 同左 |
| JSON 可解析 | — | — |
| prompt / completion tokens | — | — |
| cache hit / miss tokens | — | — |
| latency_ms | — | — |
| 费率（元/百万 tokens） | miss 2 / hit 0.04 / out 8 | 同左 |
| 本次估算费用 | **¥0** | **¥0** |
| 累计估算费用 | **¥0** | **¥0** |
| 错误类型 | **BLOCKED — 服务端未配置密钥** | 未执行 |
| 数据库前后一致性 | 无变化（见 §6） | 无变化 |

**未为了凑齐两次而发送任何请求**（授权要求：不重复发送失败请求）。

---

## 6. 结束与恢复核验（已完成）

| 要求 | 结果 |
|---|---|
| 立即关闭 DeepSeek 外部调用开关 | **已关闭**：`DEEPSEEK_EXTERNAL_ENABLED=false`，`is_ready()=False`（全程未启用） |
| 规则解释功能仍正常 | **正常**：single 与 plan 的 `mode=rules` 均返回 200、`provider=deterministic_rules`、`real_ai=false`、`externally_sent=false` |
| 未新增分配或改变床位状态 | **确认**：`beds` 44→44、`bed_allocations` 15→15、`admission_requests` 22→22、`bed_status_logs` 34→34、活动占用 5→5 |
| 真实模型请求数 ≤ 2 | **0 ≤ 2** ✔ |
| 预算控制执行情况 | 实际支出 ¥0；运行器在无密钥时于**任何网络动作之前**拒绝 |
| 数据库历史记录保持 | 床位状态分布前后一致；历史分配与流水未被触碰 |
| 不再发起真实收费请求 | 未发起；且开关保持关闭 |

`audit_logs` 134→138（+4），**全部为设计内留痕**：1 次 LOGIN、1 次只读 RECOMMEND、
2 次**被拒绝的真实 AI 尝试**（`AI_EXPLANATION_REQUEST` / `AI_PLAN_EXPLANATION_REQUEST`，
明细明确含 `no_prompt_logged:true` / `no_request_ids_logged:true`）。
详见 `docs/evidence/p4_real_pilot/api_gate_checks.md`。

> **收尾复测（14:10 再核）**：`audit_logs` 现为 **140**（新增 id 139/140，均为
> `action=RECOMMEND`、`result=SUCCESS` 的**只读**推荐留痕，`object_type=admission_request`，
> 未改动任何业务实体）。业务表计数 `beds 44 / bed_allocations 15 / admission_requests 22 /
> bed_status_logs 34 / 活动占用 5` 与床位状态分布（AVAILABLE 37 / RESERVED 2 / OCCUPIED 3 /
> CLEANING 1 / MAINTENANCE 1）**自报告生成后完全未变**；真实 DeepSeek 请求数仍为 **0/2**，
> `DEEPSEEK_EXTERNAL_ENABLED` 仍为 `false`。

---

## 7. 凭据清理风险（按授权要求记录）

本仓库为 **public**（`https://github.com/tahffo68hk-hash/attention-class`）。
经扫描，**已被 Git 跟踪**且属于「有效开发凭据」的取值分布在 **5 个文件**：

| 文件 | 凭据类型 |
|---|---|
| `backend/app/core/config.py` | 默认 `SECRET_KEY`、默认数据库连接串口令 |
| `docker-compose.yml` | 本地 MySQL root / 应用账号口令 |
| `sql/init/00_create_database.sql` | 数据库初始化口令 |
| `.env.example` | 模板中的口令占位（沿用真实开发值） |
| `backend/.env.example` | 同上 |

另有演示账号口令（`admin123`/`doctor123`/`nurse123`/`viewer123`）散见于
`backend/seed.py`、`.env.example`、`README.md`、`backend/tests/conftest.py`、
`frontend/src/views/LoginView.vue`、`frontend/e2e/smoke.spec.ts` 等，
合计约 42 处命中，均为**课程演示用占位凭据**。

**风险定级与建议**（本次**未做**相关改动，遵守「不做无关重构」边界）：

- 这些口令仅对本机隔离实例（3307）与本地演示环境有效，非生产凭据；
- 但既然仓库公开，建议后续：让 `config.py` 对 `SECRET_KEY`/DB 口令**从环境变量强制读取**、
  模板统一改为 `<YOUR_...>` 形态、并对已公开的历史提交评估是否需要轮换（本机隔离实例口令）。
- **本 Pilot 未产生任何含凭据的提交**；`.env` 未被跟踪，密钥未入库，未执行 push。

---

## 8. Git

```
b3c2a97  feat(p4): 集成 DeepSeek 可选真实 AI 解释（基线，执行前 HEAD）
cddb9cd  chore(p4-pilot): 建立 DeepSeek 真实调用 Pilot 的有界运行器与离线证据（BLOCKED：本机未配置密钥）
d8b64a0  docs(p4-pilot): 报告补充本轮引入提交号 cddb9cd
7c9871e  fix(p4-pilot): 运行器 Pilot ID 首次落盘 + 证据 .log 未被跟踪问题修正
```

- `cddb9cd` 引入本报告、证据目录与运行器（5 files changed, +1165）。
- `7c9871e` 为本轮收尾修复（5 files changed, +83/-12）。
- **本轮收尾修复**：`load_state()` 首次调用即落盘（Pilot ID 持久化）、
  证据文件名 `dry_run_console.log` → `.txt`（原后缀命中 `.gitignore:13` 的 `*.log`，
  **实际未入库**，报告引用因此失效，已修正）、彩排重跑刷新 `preflight_dry_run.json`。
- 本地提交，**未执行 `git push`（NO PUSH）**：`git log origin/main..HEAD` 显示本地领先远程。
  基线 `b3c2a97`（P4 集成）本身亦为 NO PUSH 提交。

本次新增：
- `scripts/p4_real_pilot.py`（有界运行器：持久计数 + 预算闸门 + 零网络彩排）
- `docs/P4_DEEPSEEK_REAL_PILOT.md`（本报告）
- `docs/evidence/p4_real_pilot/`（脱敏证据目录）

不入库：`backend/.env`（被 gitignore，含本地费率配置与未来密钥）、
`.workbuddy/p4_pilot_state.json`（持久计数）。

---

## 9. 解除阻塞的准确步骤（由你本人执行）

无需再向我申请授权；只需在本机补齐密钥后重跑即可：

1. 在 `backend/.env` 中填入（**仅本机，勿提交**）：
   ```ini
   DEEPSEEK_API_KEY=<你的 DeepSeek 控制台密钥>
   DEEPSEEK_EXTERNAL_ENABLED=true
   ```
   费率已按官方高峰口径预置（miss 2 / hit 0.04 / out 8 元每百万 tokens），无需改动。
2. 重启后端（使其重新加载 `.env`）：
   ```bash
   cd "E:/Attention is all you need/backend"
   <python> -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
3. 先复跑零网络彩排（确认预算与白名单仍达标）：
   ```bash
   <python> ../scripts/p4_real_pilot.py --dry-run
   ```
4. 执行被授权的两次真实调用：
   ```bash
   <python> ../scripts/p4_real_pilot.py --execute
   ```
   运行器会在每次请求**之前**占用额度并落盘，超预算或超额即拒绝；
   调用完成后请**立即**把 `DEEPSEEK_EXTERNAL_ENABLED` 改回 `false`。

> 若届时确实发生了调用，请把控制台账单/余额截图与 `execute_result.json` 一并留存，
> 以便区分「平台实际扣费」与「本地保守估算」。

---

## 10. 剩余问题与信息缺口

1. **BLOCKED 主因**：服务端缺少 API Key（唯一阻塞项）。
2. **DeepSeek request ID 不可得**：现有 `deepseek_provider._parse` 未映射响应体 `id` 字段，
   API 契约也不透出。若后续需要以 provider request ID 对账，需在 provider 层增加映射
   （属功能增强，本次未改，遵守边界）。
3. **`prompt_cache_hit_tokens` 依赖平台返回**：若平台不返回该字段，命中数按 0 计
   （即按「全部未命中」保守计费）。
4. **环境备注**：受管 Node 实际版本为 `22.22.2-6`；`agent-browser` 的 `eval` 返回值为
   带转义的 JSON 字符串（需先剥壳再解析）。
5. **凭据清理**：见 §7，建议后续单独任务处理，勿与本次 Pilot 混做。
