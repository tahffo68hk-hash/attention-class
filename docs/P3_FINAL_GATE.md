# P3 最终集成闸门报告（P3 FINAL GATE）

- 项目：**Attention is all you need** —— 医院床位智能分配与住院入院预办理（原型系统）
- 集成基线（合并前 HEAD）：`7d6789e`
- 本次 P3 集成提交：`b234175`
- 交付来源：`Attention_is_all_you_need_P3_Gate_Delta_20261014.zip`
  （`P3_INTEGRATION_GATE.md` + `BASELINE_FINGERPRINTS.json` + `P3_GATE_DELTA.patch`）
- 合并方式：**增量合并**（逐文件读差异后局部修改），**未整体覆盖**、**未重建项目**、
  **未重新合并旧 ZIP**、**未做无关重构**
- 数据边界：演示库 `hospital` 与既有历史分配数据**完整保留**，未重建、未清空
- 提交策略：**本地提交，NO PUSH**（`git push` 未执行）

---

## 0. 结论

> **P3_FINAL_GATE = PASS**

关键验收项全部通过：G1 缺陷关闭、手工状态变更保护落地、`solver=auto` 三层一致性成立、
非破坏性本地测试与真实 MySQL 测试全绿、前端类型检查与生产构建通过、浏览器**真实写入式**
业务闭环跑通并通过 31/31 一致性校验、演示库历史数据零破坏。

---

## 1. 基线指纹校验（先证明“没漂移”，再合并）

合并前先按 `BASELINE_FINGERPRINTS.json` 校验本地两个待改文件与
`P15_P25_Full_Source` 基线是否逐字节一致：

| 文件 | 交付包记录 | 本地实测 | 结论 |
| --- | --- | --- | --- |
| `backend/app/api/v1/allocations.py` | `base_sha256` | MATCH | 基线一致 |
| `backend/app/api/v1/base_data.py` | `base_sha256` | MATCH | 基线一致 |
| 两文件打完补丁后 | `patched_sha256` | MATCH | 补丁方向正确 |

结论：候选补丁是在**与本地完全相同的基线**上生成的差分，因此采用增量合并是安全的、
不会引入漂移。（`allocations.py` 本地最终实现比交付包只多一个
`UNKNOWN_OPERATOR` 常量导入，语义与交付包内联字符串「未记录（历史）」完全等价。）

---

## 2. 缺陷关闭情况

### 2.1 G1 —— 床位状态流水 `operator` / `bed_code` 此前恒为 `null`

**根因**：`/beds/{id}/status-logs` 直接返回 `operator_name=None`，且不校验床位是否存在；
前端展示为空白/“未知”，可追溯性丧失。

**修复**（`allocations.py` `bed_status_logs` + `serializers.py`）：

- 床号与操作人取自**真实关联字段**：`bed.code` / `users.full_name`（LEFT JOIN 保留旧流水）。
- 历史数据若操作人缺失，**显式标注「未记录（历史）」**（`UNKNOWN_OPERATOR`），
  **绝不编造**为“系统操作”。
- 床位不存在返回 **404 `NotFoundError`**，不再静默返回空列表。

**验证证据（浏览器闭环后 API 实测）**：

```
GET /api/v1/beds/6/status-logs
→ {"id":34,"bed_code":"C-102-02","from_status":"CLEANING","to_status":"AVAILABLE",
   "reason":"管理端手工释放","operator_name":"系统管理员", ...}
operator_name 列表: ['系统管理员','系统管理员','系统管理员','系统管理员','王芳','王芳','王芳','王芳']
```

### 2.2 手工状态变更可绕过分配/入住/出院/清洁流程

**根因**：`POST /beds/{id}/status` 直接套用全量 `BED_STATUS_TRANSITIONS`，
任何角色都能把床位从 `AVAILABLE` 手工跳到 `RESERVED`/`OCCUPIED`，绕过
分配记录、审计与清洁锚点检查。

**修复**（`base_data.py` `set_bed_status`）：

- 新增**白名单**：手工流转**只允许** `AVAILABLE ⇄ MAINTENANCE`（维护/恢复）。
- 取床改为**行级锁** `SELECT ... FOR UPDATE`（`with_for_update()`），防并发竞态。
- **拒绝**对仍存在有效分配（`RESERVED`/`OCCUPIED`）的床位直接改状态。
- 其余生命周期状态变更必须走 `reserve / admit / discharge / cancel / release`。
- 修正审计 `detail['from']` 原先取自写入后的对象（记录的是**新**状态）——改为
  写入前捕获的 `from_status`，审计现在记录**真实旧状态**。

**验证证据**：`tests_p3/test_gate_regressions.py` 中 6 组生命周期绕过组合
（`AVAILABLE→RESERVED`、`RESERVED→OCCUPIED`、`OCCUPIED→CLEANING`、
`CLEANING→AVAILABLE`、`CLEANING→MAINTENANCE`、`RESERVED→AVAILABLE`）**全部被拒**；
`MAINTENANCE` 流转审计断言 `from` 为真实旧状态；有活动分配的床位维护请求被拒。

### 2.3 `solver=auto` 实际算法 / API `method` / 前端展示三层不一致

**核实结论**：`auto` **恒为精确最小费用流**，与是否安装 OR-Tools 无关。

运行时直测（`app.services.global_optimization.optimize`）：

| backend | method | proven_optimal |
| --- | --- | --- |
| `auto` | `exact_min_cost_flow` | `True` |
| `flow` | `exact_min_cost_flow` | `True` |
| `cp_sat` | —— | 抛 `RuntimeError: CP-SAT 未安装或未能在时间限制内证明最优`（**不静默回退**） |

真实 API 实测（`POST /api/v1/optimization/preview`，`solver=auto`）：

```
optimized.method = exact_min_cost_flow
optimized.proven_optimal = True
baseline.method = greedy
```

前端（`OptimizationView.vue`）新增 `SOLVER_LABEL` 中文标签：
`exact_min_cost_flow → 精确最小费用流`、`ortools_cp_sat → OR-Tools CP-SAT`、
`greedy → 贪心回填（不保证最优）`；提示语由 `proven_optimal` 驱动
（“当前冻结候选下已证明最优” / “未证明最优”）。

→ **后端算法 = API `method` = 前端文案，三层一致。**

---

## 3. 真实 MySQL 测试（可丢弃库 `hospital_test`）

- 数据库：隔离 MySQL 8.0.32，端口 **3307**（`--no-defaults`，独立 datadir）
- 目标库：`hospital_test`（**会 TRUNCATE 全表**，与演示库 `hospital` 隔离）
- 表结构由 `alembic upgrade head` 从零建表 —— 每次跑测试都在**验证迁移脚本**

```
E:\Attention is all you need\backend> python -m pytest tests -q
======================== 57 passed, 1 warning in 112.33s (0:01:52) ========================
```

其中 P3 专项（单独复跑确认）：

```
tests/test_p3_gate_mysql.py  →  4 passed
  1) 床位流水为真实床号 + 真实操作人
  2) 手工状态不可跳过分配流程
  3) 维护流转审计捕获真实旧状态
  4) solver=auto 的 API 返回严格为精确最小成本流
```

另含 P15/P25 阶段新增的**原子换床失败回滚** 2 项
（目标床已被占用必须 409 且零副作用；违反硬约束必须 422 且零部分写入），
断言失败换床**不留下任何写入**（分配计数 / 床位状态 / 流水计数全部不变）。

---

## 4. 非破坏性本地测试

```
E:\Attention is all you need\backend> python -m pytest tests_m1_local tests_p1p2 tests_p15 tests_p25 tests_p3 -q
======================== 86 passed, 1 warning in 12.42s ========================
```

其中 P3 专项：`tests_p3/test_gate_regressions.py → 12 passed`
（G1 真实/历史/404 三例、维护流转审计、6 组生命周期绕过拒绝、活动分配拒绝、
`auto` 契约）。

> 本轮修复的一处**真实失败项**：`test_audit_invalid_window` 原先断言
> `HTTPException`，与项目统一错误契约不符 —— 后端实际抛 `BizError`
> （`code=VALIDATION_ERROR`, `status=422`）。已按契约修正断言，测试转绿。

---

## 5. 前端构建

```
E:\Attention is all you need\frontend> npm run build      # vue-tsc --noEmit && vite build
✓ 127 modules transformed.
✓ built in 2.24s        （dist/ 产物已生成，含各页面 chunk）
```

`vue-tsc --noEmit` **零类型错误**，生产构建成功。

---

## 6. 浏览器真实写入式业务闭环

- 环境：后端 FastAPI :8000 + 前端 Vite dev :5173，**真实无头浏览器**操作真实 API/DB
- 数据：**独立模拟患者** `P3闭环患者`（`patient_id=21`，仅一条，未重复建档）
- 流程：开具住院证 → 预入院登记（模拟预交金）→ 床位推荐 → 预占用 → **换床** →
  办理入住 → 办理出院 → 释放床位 → 查看床位状态流水
- 闭环结论：住院证 `ZY202610140006` 最终状态 **`COMPLETED`**

分配留痕链（同住院证 2 条，旧记录不删除、置为 `CANCELLED`）：

| 分配 | 床位 | 状态 | 说明 |
| --- | --- | --- | --- |
| #14 | C-102-03 | `CANCELLED` | 换床前预占，`cancel_reason` 含“换床至 C-102-02” |
| #15 | C-102-02 | `DISCHARGED` | 换床后：预占 → 入住 → 出院 → 释放 |

床位流水全链路（目标床）：`RESERVED → OCCUPIED → CLEANING → AVAILABLE`
（原床补记换床段释放）。两床最终均回到 `AVAILABLE`。

**闭环一致性校验（31 项，全部 PASS）** —— 覆盖 DB / API / 审计三侧：

- 住院证闭环完整、编号非空；
- 旧分配 `CANCELLED` 非删除、新分配 `DISCHARGED` 且
  `admitted_at/discharged_at/released_at` 均落库；
- 两条分配的活动唯一键均已释放（**无残留活动占用**）；
- 活动占用数回到闭环前基线（`active=5`，无半途而废的预占/入住）；
- 床位流水**全部带真实操作人**（无 `null`、无占位）；
- 审计涵盖 `REASSIGN_BED / ADMIT / DISCHARGE / RELEASE_BED`（+ `RESERVE_BED`）；
- 床位总量 44 未变；模拟患者**未重复建档**（仅 1 条）；
- 住院证/预登记/分配/流水/审计**只增不减**（历史留痕未被删除）；
- 历史分配 1–12 号记录**全部保留**；
- API 侧：床位流水返回**真实床号 + 真实操作人**、床位详情为 `AVAILABLE`、
  可查到该住院证的换床两条记录（#14 + #15）。

截图（`docs/screenshots/`）：
`p3_01_certificate.png`、`p3_02_preadmission.png`、`p3_03_recommendation.png`、
`p3_04_reserved.png`、`p3_05_reassigned.png`、`p3_06_admitted.png`、
`p3_07_discharged.png`、`p3_08_released.png`、`p3_09_status_logs.png`

---

## 7. 演示库与历史数据保全

| 对象 | 闭环前 | 闭环后 | 结论 |
| --- | --- | --- | --- |
| 床位总数 | 44 | 44 | 未增删 |
| 历史分配 1–12 号 | 12 | 12 | **全保留** |
| 活动占用数 | 5 | 5 | 回到基线，无悬挂占用 |
| 审计日志 | 75 | ≥105 | 只增不减 |

闭环产生的记录均为**新增**，历史分配记录一律以状态标记（`CANCELLED`）表达变更，
**不做物理删除**。测试全程只作用于 `hospital_test`，未触碰演示库。

---

## 8. Git

```
基线（合并前）: 7d6789e  feat(p15-p25): 集成 P15/P25 全量交付
代码集成提交  : b234175  feat(p3): 集成 P3 最终闸门增量（G1 床位流水 / 手工状态保护 / solver=auto 一致性）
                          22 files changed, 406 insertions(+), 37 deletions(-)
本报告提交    : docs(p3): 交付 P3_FINAL_GATE.md（最终 HEAD，见 `git log -1`）
```

**本地提交完成，未执行 `git push`（NO PUSH）**。

---

## 9. 剩余问题 / 已知限制

| # | 级别 | 问题 | 说明与建议 |
| --- | --- | --- | --- |
| 1 | 低 | `/allocations` 不支持按 `admission_request_id` 过滤 | 该端点已支持 `bed_id`/`patient_id`/`mode`/`department_id`，但**未声明** `admission_request_id` 参数；FastAPI 对未声明的 query 参数**静默忽略**，调用方易误判为“过滤已生效”。当前前端不使用该参数，属 API 一致性小缺口。建议后续按 `department_id` 同样写法补一个可选参数（纯增量、无破坏）。本次闸门为遵守“不做无关重构”边界**未改动**，改为在验收脚本中使用受支持参数。 |
| 2 | 低 | 隔离床分级未细分传播途径 | 是否区分空气/飞沫/接触传播仍为**待业务方确认**项（沿用既有草案）。 |
| 3 | 低 | 推荐软约束权重为草案值 | 5 项权重（距离 0.32 / 优先级-床型 0.28 / 病房负载 0.18 / 成本 0.12 / 期望病房 0.10）仍待业务方定稿。 |
| 4 | 提示 | 本地 `backend/.pytest_tmp/` 残留 | 沙箱安全删除守卫会拦截一次性批量清理，已在 `.gitignore` 中忽略；不影响仓库与运行。 |
| 5 | 提示 | `cp_sat` 分支不可用 | 本机未安装 OR-Tools，`solver=cp_sat` 会显式报错（符合设计，不做静默回退）。 |

---

## 10. 复现命令

```bash
# 后端 · 非破坏性本地测试
cd backend && python -m pytest tests_m1_local tests_p1p2 tests_p15 tests_p25 tests_p3 -q

# 后端 · 真实 MySQL 测试（写入可丢弃库 hospital_test）
cd backend && python -m pytest tests -q

# P3 专项
cd backend && python -m pytest tests_p3/test_gate_regressions.py tests/test_p3_gate_mysql.py -q

# 前端 · 类型检查 + 生产构建
cd frontend && npm run build
```
