# 核心代码对比报告 —— `Attention_is_all_you_need_P0_Core_v0.1.zip` vs 现有项目

> 对比基线：现有项目 `E:\Attention is all you need`（Git `d023453`）
> 参考包解压位置：`E:\attention-handoff\P0_Core_v0.1\attention_core_p0_v01\`（**仅解压，未覆盖、未修改现有项目**）
> 对比日期：2026-10-13
> 本报告只做对比与差异登记，**不集成、不替换、不改数据库/迁移/API**。

---

## 0. 结论摘要（先说重点）

| 维度 | 结论 |
| --- | --- |
| **隔离策略** | ✅ **已一致**：两边当前实现都是"严格双向匹配"。 |
| **硬约束 H1–H4** | ✅ 语义一致（都是4条、都是"列出全部违反项"）。命名与枚举不同。 |
| **评分公式** | ❌ **重大差异**：参考包 2 项（0.5/0.5，距离+护理适配）；现有 5 项（0.32/0.28/0.18/0.12/0.10）。两者都满足"优先级不是常数分"。 |
| **枚举值** | ❌ 多处不一致：床位状态 4 vs 5、分配状态 `CHECKED_IN` vs `ADMITTED`、优先级 3 档 vs 5 档、床型有无。 |
| **状态转换** | ⚠️ 部分一致：核心闭环一致，但**出院后床位落点不同**（参考包直接回 `AVAILABLE`；现有先到 `CLEANING` 再手动 release），且参考包有"换床 `REASSIGNED`"终态、现有没有。 |
| **事务一致性** | ⚠️ 现有**已实现**（行锁 + 唯一索引），比参考包"仅规格文档"更强；但存在 **2 个真实缺口**（缺"单住院证唯一活动分配"约束、缺幂等键）。 |
| **参考包自带测试** | 26 个纯函数用例，本地实跑 **26 passed**（无数据库，秒级）。 |
| **总的判断** | 参考包的核心价值在**纯域函数的严谨性**（成对状态校验、输入校验、逐床全原因拒绝）和**事务契约清单**；现有项目在**完整度**（住院证生命周期、清洁态、审计、权限、真实 MySQL 并发）上更完整。**不建议整体替换**，建议按"薄适配 + 逐条决策"处理。 |

---

## 1. 参考包内容清单

```
attention_core_p0_v01/
├── attention_core/
│   ├── __init__.py          导出纯域 API
│   ├── bed_rules.py         硬约束过滤 + 软评分 + 队列排序键（210 行）
│   └── state_machine.py     成对状态转移（68 行）
├── tests/
│   ├── test_bed_rules.py    15 个用例
│   └── test_state_machine.py 11 个用例
├── docs/
│   ├── DECISIONS.md                 ADR-001~004
│   ├── INTEGRATION.md               与 WorkBuddy 的集成契约
│   ├── MYSQL_TRANSACTION_CONTRACT.md 事务/幂等/并发规格
│   ├── P0_TEST_MATRIX.md            测试验收矩阵 B/S/C/A/U
│   ├── ARCHITECTURE_AND_FLOWS.md
│   └── WORKBUDDY_HANDOFF.md         交接执行指令
├── demo.py / DEMO_OUTPUT.txt / TEST_RESULTS.txt
├── pyproject.toml            仅依赖标准库；Python 3.11+（用 StrEnum）
└── README.md
```

**性质**：纯域模块，不依赖 FastAPI/SQLAlchemy，**不实现事务、鉴权、ORM、迁移**（包内 README 明确声明）。
**实测**：`python -m pytest -q` → `tests/test_bed_rules.py: 15` + `tests/test_state_machine.py: 11` = **26 项全部通过**。

---

## 2. 枚举值对比

| 概念 | 参考包 | 现有项目（`backend/app/models/enums.py`） | 差异 |
| --- | --- | --- | --- |
| 性别 | `Sex`：`FEMALE/MALE`（bed_rules L13） | `Gender`：`MALE/FEMALE`（L12） | 名称不同，**值集合相同** |
| 性别限制 | `SexLimit`：`ANY/FEMALE/MALE`（L18） | `GenderLimit`：`MALE/FEMALE/ANY`（L20） | 名称不同，**值集合相同** |
| **床位状态** | `BedStatus`：`AVAILABLE/RESERVED/OCCUPIED/OUT_OF_SERVICE`（L24）**4 个** | `BedStatus`：`AVAILABLE/RESERVED/OCCUPIED/CLEANING/MAINTENANCE`（L39）**5 个** | ❌ **不一致**：现有拆分"CLEANING（出院清洁）+ MAINTENANCE（维护）"，无 `OUT_OF_SERVICE` |
| **分配状态** | `AssignmentStatus`：`RESERVED/CHECKED_IN/DISCHARGED/CANCELLED/REASSIGNED`（L13）**5 个** | `AllocationStatus`：`RESERVED/ADMITTED/DISCHARGED/CANCELLED`（L129）**4 个** | ❌ **不一致**：`CHECKED_IN`↔`ADMITTED` 命名不同；现有无 `REASSIGNED` |
| 床型 | **无 `bed_type`**，用 `is_isolation:bool` + `care_level:1-3`（L64-71） | `BedType`：`NORMAL/ISOLATION/MONITOR`（L26）+ `is_isolation`，并有 CHECK 约束强绑定（facility L119） | ❌ **概念不同**：参考包无"监护床"概念 |
| **优先级** | `priority: int`，**1/2/3 三档**（L48） | `PatientPriority`：`CRITICAL/SEVERE/URGENT/NORMAL/MILD` **五档**（L65），`PRIORITY_RANK` 5→1（L75） | ❌ **档数不同**（3 vs 5） |
| 拒绝原因 | `Rejection` 枚举：`UNAVAILABLE/DEPARTMENT_MISMATCH/SEX_MISMATCH/ISOLATION_MISMATCH`（L31） | 无枚举，用中文 `violations: list[str]`（bed_policy L55-86） | 参考包**结构化**，现有**自然语言**；语义等价 |
| 住院证状态 | **无此概念** | `AdmissionRequestStatus` 6 态 + 流转表（L92-126） | 参考包**完全未覆盖**住院证生命周期 |
| 用户角色/审计 | 无 | `UserRole` / `AuditAction` / `AuditResult`（L165-201） | 参考包不涉及（属应用层） |

> **命名冲击**：参考包用 `Sex`/`SexLimit`/`AssignmentStatus`，现有用 `Gender`/`GenderLimit`/`AllocationStatus`。
> 若原样合并，会出现两套并行枚举。建议**保留现有命名**，仅在适配层做映射（参考包 `INTEGRATION.md` 也主张"薄适配层，不覆盖"）。

---

## 3. 隔离策略对比（重点）

| | 参考包 | 现有项目 |
| --- | --- | --- |
| 规则 | `bed.is_isolation != patient.needs_isolation` → `ISOLATION_MISMATCH`（bed_rules L127-128） | `isolation_required and not bed.is_isolation` → 违规；`not isolation_required and bed.is_isolation` → 违规（bed_policy L80-84） |
| 方向 | **严格双向** | **严格双向** |
| 文档 | `DECISIONS.md` ADR-001：明确记录"早期基线是单向（普通患者可用隔离床并扣分），本版改为严格双向" | `docs/isolation-bed-policy.md` + `POLICY_NOTES` P1/P2/P3/P5：同样严格双向 |

### ✅ 结论：两边当前策略**完全一致**，是本轮对比中唯一"零差异"的核心规则。

唯一值得注意的是：**两边都记录了同一段历史分歧**（阶段一基线是"单向 + 资源惩罚"）。参考包 ADR-001 建议"正式接入前需对齐现有策略"——本报告确认：**已对齐，无需改动**。

---

## 4. 硬约束对比

| 约束 | 参考包（`rejection_reasons` L113-129） | 现有（`hard_constraint_violations` L55-86） | 一致性 |
| --- | --- | --- | --- |
| 状态必须空闲 | `status is not AVAILABLE` → `UNAVAILABLE` | `str(bed.status) != AVAILABLE` → H1 | ✅ |
| 科室一致 | `department_id !=` → `DEPARTMENT_MISMATCH` | H2 | ✅ |
| 性别匹配 | `sex_limit is not ANY and sex_limit.value != sex.value` → `SEX_MISMATCH` | H3 | ✅ |
| 隔离匹配 | 双向 → `ISOLATION_MISMATCH` | H4（双向） | ✅ |
| 返回方式 | **一次返回全部违反项**（tuple） | **一次返回全部违反项**（list） | ✅ |

### 差异点（不冲突，但值得注意）

1. **参考包 `score_bed` 会二次校验**：对不满足硬约束的床调用评分会直接 `raise DomainInputError`（L140-141）。现有 `recommend_beds` 是"先过滤再评分"，没有这层防御——**但这个防御是好的**，可考虑吸收。
2. **参考包对输入做严格类型校验**（`PatientNeed.__post_init__` L50-60、`BedCandidate.__post_init__` L73-87）：`priority` 必须是 1/2/3 的 `int`、`distance_m` 必须非负有限（拒绝 NaN/inf）。
   现有项目没有这层域校验，靠 Pydantic（API 层）+ 数据库约束兜底。→ 参考包更早失败，**建议吸收**（防 `float('nan')` 导致的静默错排）。

---

## 5. 评分公式对比（最大差异）

### 5.1 参考包公式（`bed_rules.py` L132-156）

```
distance_score = 100 × (1 - min(distance_m, 1000) / 1000)        # 参考距离 1000 m，超出得 0
lack  = max(priority - care_level, 0)                            # 护理能力不足
excess= max(care_level - priority, 0)                            # 护理能力超出
priority_fit  = max(0, 100 - 60×lack - 15×excess)
total = 0.5 × distance_score + 0.5 × priority_fit                # 两项各 50%
排序：(-total, bed_id)                                            # L192
```

### 5.2 现有项目公式（`recommendation.py`）

| 评分项 | 权重 | 依据 |
| --- | --- | --- |
| 距离适配 `distance` | 0.32 | 欧氏加权距离（`position_x/y` + `floor×3`），**方向随优先级反转**（危重越近越好 / 轻症让出近端） |
| 优先级-床型适配 `priority_fit` | 0.28 | `BED_TYPE_FIT` 矩阵（5 优先级 × 3 床型）+ 楼层加减分 |
| 病房负载均衡 `ward_balance` | 0.18 | 优先分配到空床率更高的病房 |
| 成本适配 `cost` | 0.12 | 日费用越低越高，**敏感度随优先级变化** |
| 期望病房 `preference` | 0.10 | 命中 `preferred_ward_id` 加分 |

排序：`(-score, distance, bed_id)`（L419）

### 5.3 差异清单

| 差异 | 参考包 | 现有 | 影响 |
| --- | --- | --- | --- |
| **评分项数** | 2 项 | 5 项 | ❌ 重大 |
| **权重** | 0.5 / 0.5 | 0.32/0.28/0.18/0.12/0.10 | ❌ 重大 |
| **距离归一化** | 绝对米制，上限 1000 m | 加权距离单位，上限 `MAX_DISTANCE=60` | ❌ 不可直接换算 |
| **距离方向** | 恒定"越近越好" | 随优先级反转（`PRIORITY_PROFILE` L97-103） | ❌ 语义不同 |
| **护理适配** | `care_level` 1-3 与优先级 1-3 直接做差扣分 | `bed_type` 矩阵（无序数关系） | ❌ 需字段映射 |
| **额外维度** | 无 | 病房负载、成本、期望病房 | 现有更丰富 |
| **优先级档数** | 3 | 5 | ❌ 需映射 |
| **tie-break** | `(-total, bed_id)` | `(-score, distance, bed_id)` | ⚠️ 现有多一个键 |
| **确定性 / 稳定排序** | ✅ | ✅ | ✅ |
| **推荐不预占** | ✅（纯函数） | ✅（只读计算） | ✅ |
| **"优先级不是常数分"** | ✅（`priority_fit` 随 `care_level` 变） | ✅（`PRIORITY_PROFILE` 多维影响） | ✅ **两边都满足课程硬性要求** |

> ⚠️ **参考包 `DECISIONS.md` ADR-002 自己声明**：`total = 0.5×distance + 0.5×fit` 是"教学模拟启发式，非临床标准"，并明确"不自行新增医疗硬约束"。
> 也就是说：**参考包没有主张自己的公式比现有更正确**。权重与维度属于"待业务方确认"项（现有 `MEMORY.md` 也已把评分权重列为草案）。
> → **本轮不建议改公式**，留给用户与 ChatGPT 对齐后再定。

---

## 6. 队列排序对比

| | 参考包 `queue_priority_key`（L203-210） | 现有 |
| --- | --- | --- |
| 语义 | `(-priority, registered_sequence, patient_id)` → **优先级优先**，同级按登记序号 | `ORDER BY queue_sequence ASC`（`api/v1/queue.py` L56） |
| 结论 | ⚠️ **语义差异**：现有队列是"先到先得（纯登记顺序）"，参考包是"优先级插队"。 |

**需要业务确认**：待入院队列是否应让危重患者插队？现有实现把 `priority` 仅当**筛选参数**，不参与排序。
（现有 `Preadmission.queue_sequence` 字段本身可承载优先级权重，改动成本低。）

---

## 7. 状态转换对比（重点）

### 7.1 参考包 `apply_transition`（`state_machine.py` L40-67）—— **成对校验**

| 动作 | 前置床状态 | 前置分配状态 | 结果床状态 | 结果分配状态 |
| --- | --- | --- | --- | --- |
| `RESERVE` | `AVAILABLE` | `None` | `RESERVED` | `RESERVED` |
| `CHECK_IN` | `RESERVED` | `RESERVED` | `OCCUPIED` | `CHECKED_IN` |
| `DISCHARGE` | `OCCUPIED` | `CHECKED_IN` | **`AVAILABLE`** | `DISCHARGED` |
| `CANCEL_RESERVATION` | `RESERVED` | `RESERVED` | `AVAILABLE` | `CANCELLED` |
| `RELEASE_FOR_REASSIGN` | `RESERVED` | `RESERVED` | `AVAILABLE` | `REASSIGNED` |

### 7.2 现有项目——**两轴分别校验**

- 床位轴 `BED_STATUS_TRANSITIONS`（enums L56-62）：`AVAILABLE→{RESERVED,MAINTENANCE}`、`RESERVED→{OCCUPIED,AVAILABLE}`、`OCCUPIED→{CLEANING}`、`CLEANING→{AVAILABLE,MAINTENANCE}`、`MAINTENANCE→{AVAILABLE}`
- 分配轴 `ALLOCATION_TRANSITIONS`（L143-151）：`RESERVED→{ADMITTED,CANCELLED}`、`ADMITTED→{DISCHARGED}`
- 另有住院证轴 `ADMISSION_REQUEST_TRANSITIONS`（L110-126）——**参考包完全没有这一层**

### 7.3 差异清单

| # | 差异 | 参考包 | 现有 | 严重度 |
| --- | --- | --- | --- | --- |
| 1 | **出院后床位落点** | `OCCUPIED → AVAILABLE`（一步回到空闲） | `OCCUPIED → CLEANING`，再由独立 `release` 做 `CLEANING → AVAILABLE`（allocation L423-431 / L465-517） | ❌ **语义不同**：现有多"清洁中"中间态，且看板依赖它统计"清洁中/维护中" |
| 2 | **状态组合一致性** | ✅ 把 `(bed_status, assignment_status)` **成对**校验，可捕获"床=OCCUPIED 但分配=RESERVED"这类不一致 | ⚠️ 两轴**分别**校验，不检查配对组合 | 参考包更严谨，**建议吸收** |
| 3 | **换床终态 `REASSIGNED`** | 有专用动作 `RELEASE_FOR_REASSIGN` + 终态 | 无；换床靠"取消旧分配 + 新建分配"两条记录 | ⚠️ 现有无独立"换床"语义（历史里也看不出"这是换床"） |
| 4 | **命名** | `CHECKED_IN` | `ADMITTED` | 低（映射即可） |
| 5 | **住院证生命周期** | 无 | 6 态状态机 | 现有更完整 |
| 6 | **非法流转的报错** | `InvalidTransition`（`ValueError`） | `StateTransitionError` → HTTP 409 + `detail{from,to,allowed}` | 现有更贴合 API |
| 7 | **换床前置约束** | 仅允许入住前（`RESERVED`）换床 | 同上（入住前才能 cancel） | ✅ 一致 |
| 8 | **参考包换床需"外层事务"** | 文档标注"本包未实现事务"（L47-48） | 现有无换床 | ⚠️ 若采纳换床需自行实现双床原子事务 |

> **注意**：请**不要**把参考包的 `DISCHARGE → AVAILABLE` 直接套到现有项目——那会抹掉"清洁中"状态，与现有看板统计（清洁中 1 / 维护中 1）和 `docs/business-flow.md` 冲突。

---

## 8. 事务与并发一致性对比（重点）

### 8.1 参考包 `MYSQL_TRANSACTION_CONTRACT.md` 的 6 条要求 vs 现有实现

| # | 参考包要求 | 现有实现 | 结论 |
| --- | --- | --- | --- |
| 1 | 一张床最多一笔有效分配 | `SELECT ... FOR UPDATE` 锁床位行（allocation L220-222）+ `bed_allocations.active_bed_id` **UNIQUE 索引**（models/allocation L53-55） | ✅ **已实现**，且有并发测试（`test_concurrency.py` 3 例抢同一床） |
| 2 | 一条预登记最多一笔有效分配 | ⚠️ **无此唯一约束**；仅靠 `request.status == PRE_ADMITTED` 前置检查（allocation L160-168） | ❌ **缺口**（见 8.2） |
| 3 | 只能确认 AVAILABLE 且满足硬约束的床 | 先判状态（409）再判 H2–H4（422）（L227-248） | ✅ 已实现，且错误码分层正确 |
| 4 | 状态/分配/日志同事务提交或一起回滚 | 单 Session + `db.commit()`，异常 `rollback()`；`record_audit` **同事务**写入（L281-301） | ✅ **已实现** |
| 5 | 幂等键：同键同参返回原结果，不同参 409 | ⚠️ **无幂等键机制** | ❌ **缺口** |
| 6 | 数据库冲突统一 409，不泄露敏感数据 | `IntegrityError → ConflictError(409, BED_DOUBLE_BOOKED)`（L302-308）；错误响应统一脱敏 | ✅ 已实现 |
| 附 | 固定加锁顺序，人工调整按 bed_id 排序锁新旧两床 | 只锁**单张**床位行；未锁 request/preadmission 行 | ⚠️ 部分（详见 8.2） |

### 8.2 现有项目的两个**真实并发缺口**（本次对比新发现）

**缺口 A：缺"单住院证唯一活动分配"数据库约束**

- 现状：`active_bed_id` 唯一索引只防"**同一张床**被两条活动分配占用"，不防"**同一张住院证**占两张不同的床"。
- 风险路径：两个并发请求，分别锁住 **两张不同床位** 的行（互不阻塞），各自读取 `request.status` 仍为 `PRE_ADMITTED`，于是**同时插入两条 `RESERVED` 分配**——`active_bed_id` 唯一索引拦不住（床不同）。
- 参考包的对策（契约 §5 L50-55）：给分配表再加一个 `active_pre_admission_id` 生成列 + 唯一索引。
- 现有对策（成本更低）：在 `reserve_bed` 里**同时锁住院证行**（`SELECT ... FROM admission_requests WHERE id=? FOR UPDATE`），或补一个同类唯一索引。→ **建议登记为待修项。**

**缺口 B：无幂等键**

- 参考包要求同 `idempotency_key` 重复提交不产生第二条有效分配；现有完全没有该机制（重复点击 = 两次独立请求）。
- 现有缓解：床位被占后第二次会被 `BED_NOT_AVAILABLE` 拦住，但**若两次请求选中不同床位**则都会成功。→ **建议登记为待修项。**

### 8.3 唯一索引实现方式差异（不改，仅记录）

| | 参考包建议 | 现有 |
| --- | --- | --- |
| 方式 | `GENERATED ALWAYS AS (CASE WHEN status IN ('RESERVED','CHECKED_IN') THEN bed_id END) STORED` | 普通可空列，**应用层赋值**（reserve 写 `bed_id`，discharge/cancel 写 `NULL`） |
| 优点 | 数据库自动派生，**不可能不一致** | 无需生成列，兼容性好，迁移简单 |
| 风险 | 需新迁移；依赖列名/状态名完全匹配 | 若某条业务路径漏写 `NULL`（如新增状态忘了处理），会残留占用标记 |

> 参考包契约本身也说"WorkBuddy 可能已采用其他同等有效的约束，无须重复创建"（§5 L58）——即**不要求改装**。可留作技术债记录。

---

## 9. 数据库模型与字段映射

| 参考包字段（`INTEGRATION.md`） | 现有字段 | 状态 |
| --- | --- | --- |
| `PatientNeed.patient_id` | `patients.id` | ✅ |
| `PatientNeed.department_id` | `admission_requests.department_id`（来自住院证） | ✅ 符合契约"必须来自住院证" |
| `PatientNeed.sex` | `patients.gender` | ✅ |
| `PatientNeed.needs_isolation` | `admission_requests.isolation_required` | ✅ |
| `PatientNeed.priority`（1/2/3） | `admission_requests.priority`（5 档枚举） | ❌ 需映射（5→3 有信息损失） |
| `BedCandidate.bed_id` | `beds.id` | ✅ |
| `BedCandidate.department_id` | `beds.department_id`（真实外键） | ✅ 符合"不能按病房名模糊匹配" |
| `BedCandidate.sex_limit` | `beds.gender_limit` | ✅ |
| `BedCandidate.is_isolation` | `beds.is_isolation` | ✅ |
| `BedCandidate.status` | `beds.status` | ❌ 值集合不同（4 vs 5） |
| `BedCandidate.distance_m` | **无该列**；由 `position_x/y` + `floor` + `department.anchor_*` 实时算 | ⚠️ 概念对应，实现不同（非"米"） |
| `BedCandidate.care_level`（1-3） | **无该列**；可用 `bed_type` + `floor` 派生 | ❌ 需映射规则 |
| 事务契约中的 `bed_assignments` / `pre_admissions` / `allocation_logs` | `bed_allocations` / `preadmissions` / `bed_status_logs` | ⚠️ 表名不同（契约已声明"不能直接运行"） |

> 现有项目比参考包**多**：`departments/wards/doctors/users/audit_logs` 表，以及 `bed_allocations.score_detail(JSON)`、`BedStatusLog` 全流程留痕。
> 参考包**没有 ORM**，因此不存在"表结构冲突"，只有字段级映射问题。

---

## 10. API 响应结构对比

| | 参考包（`INTEGRATION.md` §4） | 现有（`schemas/recommendation.py`） |
| --- | --- | --- |
| 推荐项 | `{bed_id, total_score, distance_score, priority_fit_score, reason}` | `{bed_id, bed_code, ward_*, floor, bed_type, gender_limit, distance, score, score_items[5], reasons[], warnings[]}` |
| 拒绝项 | `rejected:[{bed_id, reasons:[枚举]}]` | `hard_constraint_stats`（分层计数）+ `no_result_reasons`（中文说明）**汇总形式**，不逐床返回 |
| 其他 | — | `policy_notes`、`priority_rank`、`candidates_evaluated`、`generated_at` |

**差异**：参考包**逐床**返回排除原因；现有是**分层统计 + 汇总原因**。参考包的粒度更利于前端逐床解释。
契约明确写着"可以保留原响应并映射为上述语义"（§4 L58）→ **不构成冲突**，如需逐床原因可增量扩展现有 schema。

---

## 11. 测试覆盖对照（参考包 `P0_TEST_MATRIX.md`）

| ID | 要验证 | 参考包单测 | 现有项目 |
| --- | --- | --- | --- |
| B-01 | 科室/性别/隔离/空床四条件 | ✅ | ✅ `test_recommendation.py` |
| B-02 | 普通患者不能用隔离床 | ✅ | ✅（双向隔离用例） |
| B-03 | 多原因排除并解释 | ✅ | ✅（现为汇总原因，非逐床枚举） |
| B-04 | 优先级与护理等级影响排序 | ✅ | ✅（`test_recommendation` 优先级非线性用例） |
| B-05 | 同分稳定排序与 top_k | ✅ | ✅ |
| B-06 | 非法字段/负距离/NaN | ✅（域层校验） | ⚠️ 靠 Pydantic + DB 约束，**域层无独立校验** |
| B-07 | 无符合床位返回空列表 | ✅ | ✅ |
| S-01 | 预占→入住→出院释放 | ✅（纯状态） | ✅（**真实 MySQL** 闭环） |
| S-02 | 取消预占 / 预入住调床 | ✅（单体状态） | ⚠️ 有取消，**无 REASSIGNED 调床** |
| S-03 | 非法重复状态变更被拒 | ✅ | ✅（4 类非法流转用例） |
| C-01 | 两人竞争同一床位 | ❌ 未做（需 MySQL） | ✅ **真实 MySQL 双线程**（3 例） |
| C-02 | 同一患者并行占两床 | ❌ 未做 | ❌ **未覆盖**（见 8.2 缺口 A） |
| C-03 | 幂等键重复/参数冲突 | ❌ 未做 | ❌ **未实现**（见 8.2 缺口 B） |
| C-04 | 写日志中途失败回滚 | ❌ 未做 | ⚠️ 未显式做故障注入 |
| A-01 | 医生/管理员权限隔离 | ❌ 未做 | ✅ `test_auth_audit.py`（12 例） |
| A-02 | 敏感字段脱敏 + 审计可追溯 | ❌ 未做 | ✅ |
| U-01 | 浏览器闭环 | ❌ 未做 | ⚠️ 仅有首页/状态页（业务页未实现） |
| U-02 | 看板数字与床位状态一致 | ❌ 未做 | ✅ 看板统计已校验 |

**规模**：参考包 26 个纯函数用例（**0 依赖**）；现有 44 个用例（**含真实 MySQL 并发/权限/审计**）。
**性质差异**：参考包验证"规则本身对不对"；现有验证"规则在真实系统里跑不跑得通"。**两者互补，不能互相替代**（参考包 README 也明确禁止混淆）。

---

## 12. 已满足要求的部分（可保留，无需改动）

1. ✅ **隔离策略**：严格双向匹配，与参考包当前选择完全一致（`bed_policy.py` L80-84）。
2. ✅ **四条硬约束语义**：状态/科室/性别/隔离，且都是"列出全部违反项"。
3. ✅ **优先级非退化**：两边都保证"同一张床对不同优先级患者得分不同"。
4. ✅ **确定性排序**：两边都有稳定 tie-break，不依赖输入顺序。
5. ✅ **推荐不产生副作用**：都是纯计算，不预占、不落库。
6. ✅ **无床位返回明确原因**：现有 `no_result_reasons` 覆盖 P5 不降级、隔离床独占等场景。
7. ✅ **床位唯一占用**：`FOR UPDATE` + 唯一索引，已用真实 MySQL 并发测试证明。
8. ✅ **事务一致性**：状态/分配/审计同事务，异常整体回滚。
9. ✅ **冲突→409**：错误码分层（409 冲突 / 422 硬约束不符）符合契约第 6 条。
10. ✅ **脱敏与审计**：契约要求"核心层不做鉴权、由 API 层授权"——现有实现正是这样分层。

---

## 13. 规则 / 实现差异清单（汇总，供决策）

| # | 差异 | 参考包 | 现有 | 位置 | 建议 |
| --- | --- | --- | --- | --- | --- |
| D1 | 评分维度与权重 | 2 项 / 0.5+0.5 | 5 项 / .32+.28+.18+.12+.10 | `bed_rules.py` L132-156 ↔ `recommendation.py` L57-63 | **待用户与 ChatGPT 确认**，本轮不动 |
| D2 | 床位状态集合 | 4 态（含 `OUT_OF_SERVICE`） | 5 态（含 `CLEANING`/`MAINTENANCE`） | `bed_rules.py` L24 ↔ `enums.py` L39 | **保留现有**（看板与流程依赖清洁/维护态） |
| D3 | 分配状态命名 | `CHECKED_IN` | `ADMITTED` | `state_machine.py` L14 ↔ `enums.py` L131 | 保留现有，映射即可 |
| D4 | 换床终态 | `REASSIGNED` | 无 | `state_machine.py` L18 ↔ `enums.py` L129 | **待确认**是否引入 |
| D5 | 出院落点 | `OCCUPIED→AVAILABLE` | `OCCUPIED→CLEANING→AVAILABLE` | `state_machine.py` L56-58 ↔ `allocation.py` L423-431 | **保留现有**（勿抹掉清洁态） |
| D6 | 状态配对校验 | ✅ 成对 | ❌ 分轴 | `state_machine.py` L40-67 ↔ `allocation.py` L89-117 | **可吸收**（增强一致性检查） |
| D7 | 优先级档数 | 3 | 5 | `bed_rules.py` L48 ↔ `enums.py` L65 | 保留现有，映射 |
| D8 | 床型概念 | 无（用 `care_level`） | 3 类 `BedType` | `bed_rules.py` L64-71 ↔ `facility.py` L89 | 保留现有 |
| D9 | 距离口径 | 米 / 1000 m 上限 | 加权距离 / 60 上限 | `bed_rules.py` L143 ↔ `recommendation.py` L74 | 保留现有 |
| D10 | 队列排序 | 优先级优先 | 登记序号优先 | `bed_rules.py` L203-210 ↔ `queue.py` L56 | **待业务确认** |
| D11 | 域层输入校验 | ✅ 严格（拒 NaN/inf/非法枚举） | ❌ 无 | `bed_rules.py` L50-87 ↔ 无 | **建议吸收**（低成本、防静默错排） |
| D12 | 幂等键 | 要求实现 | 未实现 | 契约 §1.5 ↔ 无 | **登记为待修项** |
| D13 | 单住院证唯一活动分配 | 要求唯一索引 | 仅靠状态前置检查 | 契约 §5 ↔ `models/allocation.py` L53 | **登记为待修项**（真实并发缺口） |
| D14 | 加锁范围/顺序 | 锁 pre_admission + bed，按 bed_id 排序 | 只锁单张 bed | 契约 §2/§3 ↔ `allocation.py` L220 | 与 D13 一并处理 |
| D15 | 唯一索引形态 | 生成列（STORED） | 普通列 + 应用层赋值 | 契约 §5 ↔ `models/allocation.py` L53 | 保留现有，记技术债 |
| D16 | 拒绝原因粒度 | 逐床枚举 | 分层统计 + 汇总中文 | `bed_rules.py` L106-110 ↔ `schemas/recommendation.py` L39-49 | 可选增强 |
| D17 | 住院证生命周期 | 未覆盖 | 6 态状态机 | — ↔ `enums.py` L92-126 | 保留现有 |
| D18 | 表名 | `bed_assignments` 等 | `bed_allocations` 等 | 契约 ↔ 现有 schema | 无需改（契约已声明不可直接运行） |

---

## 14. 需要用户 / ChatGPT 拍板的决策点

1. **评分公式以谁为准？**（D1）现有 5 项 vs 参考包 2 项，权重与维度完全不同。
   → 参考包自己声明是"教学启发式、非临床标准"；现有 `MEMORY.md` 也把权重列为草案。**需业务确认。**
2. **是否引入"换床（REASSIGNED）"语义？**（D4）需配套双床原子事务（参考包未实现）。
3. **待入院队列是否按优先级插队？**（D10）
4. **是否补幂等键与"单住院证唯一分配"约束？**（D12/D13）—— 属**真实并发缺陷**，建议至少修 D13。
5. **是否吸收"成对状态校验"和"域层输入校验"？**（D6/D11）—— 低成本、纯增强，风险最低。

---

## 15. 最小集成建议（**本轮不执行**，仅备选）

> 依 `WORKBUDDY_HANDOFF.md` 的第 2 条：优先复用纯函数 + 薄适配层，不因示例字段大改现有 ORM。

1. **零风险（推荐优先做）**
   - 把参考包的**域层输入校验**（`PatientNeed/BedCandidate.__post_init__`）以校验函数形式并入 `bed_policy`（D11）；
   - 把**成对状态校验**思路并入 `allocation._transition_bed`，作为额外断言（D6）；
   - 补 `active_pre_admission_id` 唯一约束或住院证行锁（D13）——**这是真缺陷**。
2. **中等风险**
   - 在保留现有响应结构的前提下，**增量**增加逐床 `rejected` 明细（D16）；
   - 队列排序增加优先级维度（D10，需业务确认）。
3. **高风险（本轮明确不做）**
   - 替换评分公式（D1）；
   - 改床位/分配枚举集合（D2/D5/D7/D8）——会牵动迁移、看板、流程文档、测试；
   - 引入 `REASSIGNED` 换床流程（D4）——需新事务与迁移。

**统一约束**：任何集成都需先跑现有 44 项测试（真实 MySQL），再补针对性用例；不得声称"包内纯函数通过 = P0 完整验收"。

---

## 16. 环境与验证记录

- 参考包解压：`E:\attention-handoff\P0_Core_v0.1\attention_core_p0_v01\`（未触碰现有项目任何文件）。
- 参考包自带测试实跑：`tests/test_bed_rules.py` 15 + `tests/test_state_machine.py` 11 = **26 passed**（纯函数，秒级，无数据库）。
- 现有项目基线：Git `d023453`，其 44 项测试为本报告直接引用（本轮**未重跑**，按要求）。
- 现有项目文件、迁移、API、数据库：**本轮均未修改**。
