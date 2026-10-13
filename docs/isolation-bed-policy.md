# 隔离床使用策略

> 与代码同源：`backend/app/services/bed_policy.py` 的 `POLICY_NOTES`
> 与 `hard_constraint_violations()` 实现，本文件是它的自然语言版本。
> 策略参数（何种感染类型对应何种隔离等级）仍待业务确认，当前为原型约定。

## 术语

| 术语 | 含义 |
| --- | --- |
| 隔离患者 | 住院证 `isolation_required = true` 的患者 |
| 隔离床 | 床位 `is_isolation = true`（等价于 `bed_type = ISOLATION`） |
| 普通床 | `is_isolation = false` 的床位（`NORMAL` / `MONITOR`） |

## 策略条款

| 编号 | 条款 | 实现位置 |
| --- | --- | --- |
| **P1** | 隔离患者**只能**分配到隔离床。分配到普通床属于硬约束违规（H4），推荐阶段直接淘汰，人工选择时返回 `422 HARD_CONSTRAINT_VIOLATION`。 | 推荐过滤 + 人工校验 |
| **P2** | 隔离床**只对隔离患者开放**。非隔离患者即使本科室普通床已满、隔离床空置，也不得占用。目的是避免隔离资源被挤占、保持隔离单元感控完整性。 | 推荐过滤 + 人工校验 |
| **P3** | 隔离床空置时状态仍为 `AVAILABLE`（看板上计入「空床」），但不会进入非隔离患者的候选集，而是计入 `hard_constraint_stats.excluded_by_isolation`，并出现在无床原因说明中。 | `scan_candidates` |
| **P4** | 隔离床的性别限制独立生效：`gender_limit` 为 `ANY` 时任意性别可用；若设为仅限某一性别，则另一性别患者不可使用（H3）。 | `hard_constraint_violations` |
| **P5** | 隔离患者无可用隔离床时**直接返回原因**，**不做降级**到普通床的处理。 | `_build_no_result_reasons` |

## 数据库级一致性

隔离属性与床型必须一致，由 CHECK 约束保证：

```sql
CONSTRAINT ck_beds_isolation_consistent CHECK (
  (bed_type = 'ISOLATION' AND is_isolation = 1)
  OR (bed_type <> 'ISOLATION' AND is_isolation = 0)
);
```

即：`bed_type = 'ISOLATION'` ⟺ `is_isolation = 1`。接口层在新增/修改床位时
会自动推导该字段，避免调用方传错。

## 看板口径

隔离床在看板上单独统计，便于感控管理：

| 指标 | 口径 |
| --- | --- |
| `isolation_beds_total` | `is_isolation = true` 的床位总数 |
| `isolation_beds_available` | 隔离床中状态为 `AVAILABLE` 的数量 |
| `isolation_beds_in_use` | 隔离床中状态为 `RESERVED` 或 `OCCUPIED` 的数量 |

注意：`isolation_beds_available` 会计入总「空床」数，但这部分空床**不向非隔离患者开放**。
两者口径差异是有意为之，需在使用看板时注意。

## 待业务确认的问题

以下是本次实现中做的**假设**，需要业务方复核后再定稿：

1. 是否需要按感染类型细分隔离等级（空气传播 / 飞沫传播 / 接触传播）并做**床-病匹配**？
2. 隔离床是否需要「缓冲期」（使用后强制空置 N 小时）？当前仅通过 `CLEANING` 状态间接表达。
3. 隔离患者是否可以与同种感染患者共用隔离病房（同病房合并收治）？
4. 隔离床是否允许非隔离患者**临时**使用（如应急扩容）？当前策略为完全禁止。
