# Attention is all you need — M1 真实工程修复补丁 v0.5

## 范围与来源

基于用户提交的 REVIEW_SOURCE.zip (WorkBuddy 导出的实际后端代码) 修改；不是平行示例项目。
只覆盖 PATCH/ 下列出的文件；现有五维评分、隔离策略、五态床位不变。
不含密钥和 .env。生成包不直接修改 Windows 上的工程。

## 实现

- G5：`bed_allocations.active_request_id` MySQL STORED generated column，
  仅在 RESERVED/ADMITTED 时取 admission_request_id，其它状态 NULL；唯一约束防同住院证双床。
  同时 reserve 先锁住院证后锁床位，admit/discharge/cancel 统一锁序，防并发业务竞态。
- G6：`allocation_idempotency` 表的 `request_key` 唯一 + 请求体 SHA-256。
  `POST /api/v1/allocations` 支持可选 `Idempotency-Key` header (ASCII 8–128)。
  同键同参返回原 allocation id（当前资源表示），同键异参 409 IDEMPOTENCY_KEY_CONFLICT。
  省略 header 保留旧 API 行为，但仅依赖申请唯一约束，不具备重试复用保证。
- 新增 `POST /api/v1/allocations/{id}/reassign`：仅预占用状态可人工换床，
  必填 `new_bed_id`、`reason`；旧记录 CANCELLED，生成新 RESERVED，
  床位状态、成功审计统一事务，失败全部回滚。
- `admit/discharge/cancel` 增加床位与分配状态成对校验。
- 没有改动既有 recommendation.py 的五维评分或 bed_policy.py 的硬约束。

## 与当前前端的兼容

- 旧 `POST /allocations` 请求体、响应结构未改；新 header 可选，不影响现有前端。
- 新 reassign API 暂无对应前端按钮，由 WorkBuddy 后续 UI 集成。
- 多次使用相同幂等键必须保证用户意图相同；一次新操作生成新键（建议 UUID）。
- 重试同键返回的是**原分配记录的当前表示**，不保证原始时刻响应状态快照不变。

## 集成顺序（由 WorkBuddy 本地执行）

1. 确认仓库 HEAD 与修改情况，先对照 REVIEW_DIFF.patch 审查；若存在后续改动先合并，而非盲目覆盖。
2. 不要直接修改现有 `573c803013d2_init_schema.py`。新增迁移 `9bca1026e001`。
3. 先验证工作在隔离的 `hospital_test`，千万不要用生产库；现有 `tests/conftest.py`
   会 DROP 并重建其指向测试库的**所有表**！
4. 先核实 `settings.TEST_DATABASE_URL` 确实指向独立的 `hospital_test`，
   与演示库 `hospital` 不同，且不包含任何真实数据。之后执行 `pytest -q`；
   该测试套件会使用测试 URL **自动 DROP / 重新迁移所有测试表**，无需提前手动在测试库 `alembic upgrade`。
   记录原有 44 项 + 新增测试的真实结果。
5. 重点运行 `pytest -q tests/test_m1_concurrency.py tests/test_concurrency.py`
   （MySQL 8.0，两个线程独立连接），必须提供实际测试输出。
6. 用当前演示项目数据库先做备份、检查是否有同住院证多条活动记录，再执行
   只增量的 `alembic upgrade head`；迁移遇重复活动分配会主动失败，禁止自动清除历史。
7. API 回归：旧分配/入住/出院/释放/取消，以及新幂等/换床、日志、登录权限。
8. 前端 build 和关键浏览器流程；本地 commit，NO PUSH。

### MySQL 迁移前异常数据检查

```sql
SELECT admission_request_id, COUNT(*) AS n FROM bed_allocations
WHERE status IN ('RESERVED','ADMITTED')
GROUP BY admission_request_id HAVING COUNT(*) > 1;
```

必须 0 行。若非 0，不要擅自删除数据；先检查原始记录。

### API 样例（前端后续加入）

```http
POST /api/v1/allocations
Authorization: Bearer <token>
Idempotency-Key: 3b97b92c-28d6-4c0b-9cbb-7785e2b8edba
Content-Type: application/json

{"admission_request_id":1,"bed_id":2}
```

```http
POST /api/v1/allocations/10/reassign
Authorization: Bearer <token>
Content-Type: application/json

{"new_bed_id":3,"reason":"人工调整位置"}
```

## 独立验证（本环境）

- Python 3.13.5 + SQLAlchemy 2.0.50，源码 compileall 通过。
- `pytest -q tests_m1_local/test_m1_sequential.py`：11/11 PASS，SQLite 顺序逻辑。
- SQLite 故障注入：换床旧记录失活后注入异常，回滚成功。
- MySQL 方言模型 DDL 编译成功；MySQL 实际迁移/并发尚未验证（当前环境无 mysqld/PyMySQL）。
- WorkBuddy 原有 44 项需要其 MySQL 环境执行，**不能宣称回归通过**。

## 边界和后续

- 目前幂等保护覆盖分配预占 API；换床/入住等动作仍使用现有状态机防重复，
  若有网络重试精确同响应的需求，可后续扩展幂等策略。
- `active_bed_id` 仍是应用层维护字段（旧数据库约束）；新增申请约束为生成列，
  避免应用漏清理。后续可考虑将床位端也改为数据库生成列，但不在本轮扩范围。
- status logs 中 operator_name 为 null（G1）及队列优先级（G7）本轮未修改。
- 导出包曾在 config.py 中脱敏默认凭证，生产用应改为强制环境配置。
