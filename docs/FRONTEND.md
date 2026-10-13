# 前端管理后台说明与接口缺口登记

> 本轮范围内：**只做页面与前后端集成**。
> 未修改推荐引擎、事务服务、状态机、数据库结构与迁移。
> 页面遇到后端能力不足时，**不自行改造核心事务**，统一登记在本文档第六节。

---

## 一、页面清单

| 路由 | 文件 | 说明 |
| --- | --- | --- |
| `/login` | `views/LoginView.vue` | 账号口令登录，提供 4 个演示账号一键填充 |
| `/dashboard` | `views/DashboardView.vue` | 管理看板 |
| `/admissions` | `views/AdmissionsView.vue` | 住院证列表 + 开具 + 预入院登记 |
| `/recommendations` | `views/RecommendationView.vue` | 床位推荐结果与可解释评分 |
| `/beds` | `views/BedsView.vue` | 床位多维护筛选 / 状态流水 / 手工调状态 / 释放 |
| `/allocations` | `views/AllocationsView.vue` | 分配记录 + 预占用 / 入住 / 出院 / 取消 |
| `/audit` | `views/AuditView.vue` | 审计日志检索（仅管理员） |
| `/system-status` | `views/SystemStatusView.vue` | 前后端连通性与后端服务信息 |

公共组件：`components/StatusBadge.vue`（中文状态徽标）、`components/Pager.vue`（分页）、
`components/Modal.vue`（模态框）。

## 二、认证与权限

* 登录成功后令牌写入 `localStorage`（键 `hba.token`），用户信息写入 `hba.user`。
* `api/http.ts` 的请求拦截器统一注入 `Authorization: Bearer <token>`；
  响应 401 时清理本地会话并跳回 `/login`（登录接口自身除外，避免死循环）。
* `router/index.ts` 的全局守卫：`meta.requiresAuth` 且无令牌 → 跳登录页。
* `stores/auth.ts` 暴露能力位，页面据此显隐按钮：

| 能力位 | 角色 | 影响页面 |
| --- | --- | --- |
| `canIssueCertificate` | 医生 / 管理员 | 住院证页：开具、取消 |
| `canPreadmit` | 护士 / 医生 / 管理员 | 住院证页：预入院登记 |
| `canOperateAllocation` | 护士 / 管理员 | 推荐页、床位页、分配页的操作按钮 |
| `canRevealPatients` | 仅管理员 | 患者明文（本轮未做页面入口） |

> 页面隐藏按钮只是体验优化；**后端仍是最终关口**，越权请求返回 `403 PERMISSION_DENIED` 并写审计。

## 三、页面 → 接口映射

### 管理看板 `/dashboard`

| 数据 | 接口 |
| --- | --- |
| 全部统计（总床位 / 空床 / 预占用 / 已入住 / 清洁中 / 维护中 / 占用率 / 待入院人数 / 隔离床 / 分科室统计 / 队列优先级分布） | `GET /api/v1/dashboard/summary` |

### 住院证与预登记 `/admissions`

| 操作 | 接口 |
| --- | --- |
| 列表（科室 / 状态 / 优先级 / 隔离 / 编号搜索） | `GET /api/v1/admission-requests` |
| 开具（可选择直接开具或存草稿） | `POST /api/v1/admission-requests`（`issue` 字段） |
| 草稿开具 | `POST /api/v1/admission-requests/{id}/issue` |
| 取消 | `POST /api/v1/admission-requests/{id}/cancel` |
| 预入院登记（模拟预交金） | `POST /api/v1/admission-requests/{id}/preadmission` |
| 下拉选项 | `GET /api/v1/patients`、`GET /api/v1/departments`、`GET /api/v1/doctors`、`GET /api/v1/wards` |

### 床位推荐 `/recommendations`

| 操作 | 接口 |
| --- | --- |
| 待入院住院证列表 | `GET /api/v1/admission-requests?status=PRE_ADMITTED` |
| 推荐结果 | `GET /api/v1/admission-requests/{id}/bed-recommendations?limit=N` |
| 采纳推荐第一名 | `POST /api/v1/allocations` body `{admission_request_id, confirm_top_recommendation: true}` |
| 人工选择床位 | `POST /api/v1/allocations` body `{admission_request_id, bed_id}` |

页面展示 `score_items` 五项明细（原始分 / 权重 / 贡献 / 说明）、`reasons`、`warnings`；
无候选时展示 `no_result_reasons` 与 `hard_constraint_stats` 的排除计数。

### 床位管理 `/beds`

| 操作 | 接口 |
| --- | --- |
| 列表（科室 / 病房 / 状态 / 床型 / 隔离 / 性别 / 关键字） | `GET /api/v1/beds` |
| 状态流水 | `GET /api/v1/beds/{id}/status-logs` |
| 手工调状态（仅管理员） | `POST /api/v1/beds/{id}/status` |
| 释放床位（清洁中 → 空闲） | `POST /api/v1/beds/{id}/release` |

前端维护了一份 `BED_STATUS_TRANSITIONS` 的本地副本，**仅用于下拉展示合法目标状态**；
实际校验以后端状态机为准（非法流转返回 `409 ILLEGAL_STATE_TRANSITION`）。

### 分配与住院办理 `/allocations`

| 操作 | 接口 |
| --- | --- |
| 分配记录列表（状态 / 科室 / 方式） | `GET /api/v1/allocations` |
| 新建预占用 | `POST /api/v1/allocations` |
| 办理入住 | `POST /api/v1/allocations/{id}/admit` |
| 办理出院（床位转清洁中） | `POST /api/v1/allocations/{id}/discharge` |
| 取消预占用（床位回空闲） | `POST /api/v1/allocations/{id}/cancel` |

### 操作审计 `/audit`

| 操作 | 接口 |
| --- | --- |
| 日志列表（操作人 / 动作 / 对象 / 结果） | `GET /api/v1/audit-logs` |

## 四、数据类型约定

后端 `Decimal` 字段（`daily_rate`、`deposit_amount`、`AllocationRead.score`）经 Pydantic
序列化为**字符串**（如 `"120.00"`），因此前端类型声明为 `string`，展示时统一 `Number(...).toFixed(2)`。
所有枚举均以 `name` 字符串传输（与后端 `enum.StrEnum` 的 `value` 一致）。

## 五、开发与构建

```powershell
cd "E:\Attention is all you need\frontend"
npm install
npm run dev          # 开发服务器 http://127.0.0.1:5173
npm run build        # vue-tsc --noEmit && vite build
```

`vite.config.ts` 将 `/api`、`/health`、`/docs`、`/redoc`、`/openapi.json` 代理到 `127.0.0.1:8000`。

---

## 六、接口缺口登记（**本轮不修，待核心规则确认后再最小化补齐**）

| 编号 | 缺口 | 影响 | 建议的最小化补法（不改核心事务） | 严重度 |
| --- | --- | --- | --- | --- |
| G1 | `GET /beds/{id}/status-logs` 的 `bed_code` 与 `operator_name` 被硬编码为 `null`（见 `backend/app/api/v1/allocations.py` 的 `bed_status_logs`） | 床位页的状态流水**无法显示操作人**与床位号，只能显示时间与前后状态 | 在路由层补 `joinedload` 查询并填充这两个字段（纯读接口，不涉及事务与状态机） | 中 |
| G2 | `BedStatusLog` 模型未关联 `operator` 关系（只有 `operator_id`），序列化时拿不到姓名 | 同 G1 | 给模型加 `operator` relationship（**改模型文件，属核心侧改动**，交给 ChatGPT） | 中 |
| G3 | `GET /admission-requests` 的 `keyword` **仅匹配住院证编号**，不含患者姓名 | 住院证页无法按患者姓名搜索，只能按编号 | 路由层把 `keyword` 扩展为 `certificate_no OR patient.name`（需 join，纯查询） | 低 |
| G4 | `GET /audit-logs` 无时间范围（`date_from` / `date_to`）筛选 | 审计页只能翻页，无法按时间段检索 | 路由层加两个可选时间参数（纯查询） | 低 |
| G5 | 无「单住院证唯一活动分配」约束（`CORE_COMPARISON.md` D13） | 并发下同一住院证理论上可占两张不同床位；前端已用「操作后重新拉取列表」缓解，但非根治 | 由核心侧负责（生成列 + 唯一索引，或 reserve 时锁住院证行） | 高 |
| G6 | 无幂等键（`CORE_COMPARISON.md` D12） | 前端重复点击会重复提交；页面已用 `busyId` 禁用按钮缓解，但网络重试仍可能重复 | 由核心侧负责（`Idempotency-Key` + 结果回放） | 中 |
| G7 | 待入院队列 `GET /preadmissions` 按 `queue_sequence` 排序，**未按优先级插队** | 推荐页左侧列表顺序与病情紧急度不一致（页面已显示优先级徽标以便人工判断） | 属业务规则决策（`CORE_COMPARISON.md` D10），确认后再改 | 中 |
| G8 | 缺少「按患者维度查询其历史住院证 / 分配」的接口 | 无法做患者 360° 视图 | 需要时新增只读聚合接口 | 低 |
| G9 | `GET /patients` 的 `reveal=true` 需管理员，且会写审计 | 页面未提供明文切换入口（避免误触产生大量审计） | 后续按需增加带二次确认的入口 | 低 |

> **G5 / G6 / G7 属核心一致性或业务规则范畴，按分工由 ChatGPT 侧负责**；
> 本轮前端只做体验层缓解（按钮禁用、操作后刷新、优先级徽标提示），未触碰事务实现。

---

## 七、本轮通过真实浏览器修掉的真实缺陷

### F1　推荐页得分百分比恒为 100%（已修）

* **现象**：床位推荐页四张候选床的得分进度条与百分比**全部显示 `100%`**。
* **根因**：后端 `BedRecommendation.score` 是**0–100 分制**（各 `score_items.contribution` 之和，
  实测首位为 `86.5500`）；前端 `scorePct()` 误按 **0–1 归一**处理，
  `Math.min(1, 86.55)` 被截断为 `1` → 显示 100%。
* **修复**：`scorePct()` 改为按 100 分制取整（`Math.max(0, Math.min(100, score))`）。
* **教训**：**HTTP 200 与接口字段齐全都不代表页面正确**——这类比例尺错误只有把页面渲染出来才看得见。
  与 M0 阶段的「服务信息四项空白」是同一类问题（HTTP 看不出、浏览器里一眼看穿）。

### F2　服务信息四项空白（M0 阶段已修，记录备查）

前端 `fetchServiceInfo()` 请求 `/`，但 Vite 只代理 `/api` 与 `/health`，`/` 被 dev server
截获返回 `index.html`，导致系统状态页「后端服务信息」四项为空。
已改为后端新增 `GET /api/v1/system/info` 并让前端调用该路径。

