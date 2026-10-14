# Attention is all you need — P1.5 / P2.5 实现与验收（2026-10-14）

## 结论与事实边界

**代码已在 v1.1 候选源码上完成；并非已集成用户的 Windows 本地仓库。**

- P1.5：真实调用现有 `hard_constraint_violations` 与五维评分分项函数，在完全虚构的合成患者/床位静态快照上执行 81 个实验场景（3 种需求规模 × 3 种床位供给比 × 3 种隔离比例 × 3 个种子）。CSV/JSON 输出可复现。
- P2.5：真实 SQLAlchemy ORM + FastAPI TestClient 的顺序 HTTP 业务闭环、事务故障注入、非法重复状态转移、测试库防误删除保护，以及待 Windows MySQL 环境执行的双连接并发换床与 DB 约束测试。
- 本地 `pytest`: **74 passed**，原版 56 项 + 本轮 18 项（5 P1.5 / 13 P2.5），真实 MySQL 测试不在其中。
- 尚未测试：真实 MySQL 并发/原有 MySQL 44 项回归、Windows 最新源码集成、真实浏览器 Playwright、Docker 与真实 OR-Tools CP-SAT。

## P1.5：实验设计

运行：

```bash
PYTHONPATH=backend python scripts/benchmark_matrix.py --output-dir docs/experiments/p15
cd backend && python -m pytest -q tests_p15
```

核心边界：
1. 每个场景创建虚构患者和床位的**静态快照**；床位已有占用按 `OCCUPIED` 处理。只匹配满足 H1 状态、H2 科室、H3 性别、H4 严格隔离匹配的边。
2. 每条候选边调用当前项目五维评分的同源计算函数（距离、床型与优先级适配、病房空闲率、费用、偏好），重用权重和小数舍入规则；它不重新发明 0–100 分数。
3. Greedy 与精确最小费用流输入**完全相同**，目标按 `(安排人数, 优先级和, 总评分)` 字典序比较，评分和及耗时各自单独记录。
4. 每个场景输出匹配人数、优先级和、评分和、危重/重症服务率、运行时间、候选关系数及 SHA256 数据指纹；汇总包含中位数和 P95。即使总优先级变好，也**不保证每种优先级人群都单调变好**。
5. 随机性来自固定种子，构造和数据指纹可复现；CPU 耗时取决于硬件与负载，**不要求跨机器完全一致**。

### 本容器实测（81 组）

| 指标 | Greedy | 精确全局优化 |
| --- | ---: | ---: |
| 总安排次数（跨 81 场景累计，不是独立患者数） | 1023 | 1040 |
| 安排人数提高的场景 | — | 14 / 81 |
| 安排人数持平但优先级和提高的场景 | — | 7 / 81 |
| 单批求解耗时中位数 | 0.108 ms | 1.021 ms |
| 单批求解耗时 P95 | 0.568 ms | 10.426 ms |

结果取自 `docs/experiments/p15/summary.json`。这些耗时是本容器的**纯求解过程**，不包含数据库查询、前端渲染、网络或实际分配事务。结果只能证明合成数据上的实现差异，不能外推为临床效果。

### 关键文件
- `scripts/benchmark_matrix.py`：CLI、多因素场景生成、报告汇总
- `docs/experiments/p15/scenario_results.csv`：81 行原始实验结果
- `docs/experiments/p15/summary.json`：整体汇总与供需/隔离二维分组
- `backend/tests_p15/test_matrix.py`：输入可复现、目标不退化、空候选、报表契约

## P2.5：可靠性覆盖

### 当前可运行的本地测试（SQLite 顺序逻辑，不代表 MySQL 并发）

- 预占用事务的审计失败故障注入：床位仍为空闲，分配/流水/幂等记录均无残留，幂等键可重试。
- 入住、出院、取消预占、清洁释放事务的审计异常：床位状态与分配状态均回滚，流水数量不增加。
- 对入住、出院、取消的重复非法状态转移返回业务错误。
- 用 `TestClient` 通过真实 HTTP API：预占→同键重试→同键异参 409→换床→入住→出院→清洁完成→床位再次空闲，核对历史分配与操作审计。
- API 参数错误不写入分配；越权返回 403，记录拒绝审计；优化预览和辅助解释不写入分配。
- 测试库安全：误将 `TEST_DATABASE_URL` 指向 `hospital` 会在连接或删表前拒绝执行。

### 仅编写、尚待 Windows MySQL 运行的测试

`backend/tests/test_p25_mysql_reliability.py`：两个事务同时把不同预占患者换到同一目标床位，至多一个成功；失败者保有原床。第二项直接绕开服务写两条同申请活动分配，断言数据库生成列唯一索引阻止第二条。

**严禁**在真实医院、演示或生产库运行正式 MySQL 夹具：`backend/tests/conftest.py` 会 **DROP / TRUNCATE** 测试库中的全部表，本轮已加上 `hospital_test` 数据库名校验。

### Windows 本地验证指令（只针对可销毁的 hospital_test）

```powershell
cd 'E:\Attention is all you need\backend'
# 确保 TEST_DATABASE_URL 指向独立 hospital_test，不是 hospital。这里的测试会重建其全部表。
python -m pytest -q tests
python -m pytest -q tests_m1_local tests_p1p2 tests_p15 tests_p25
cd ..
python scripts/benchmark_matrix.py --output-dir docs/experiments/p15
```

浏览器烟测脚本为 `frontend/e2e/smoke.spec.ts`。它只面向候选版 Vue 前端登录与页面导航，不包含写操作；本地设置仅供演示的 `E2E_USERNAME`/`E2E_PASSWORD` 后执行 `npm run test:e2e`。Playwright 浏览器需要先单独安装；此脚本尚未在本容器内启动浏览器验证。如果采用 WorkBuddy 当前另一套前端，需要适配登录选择器和页面路径，不可盲套候选版脚本。

## 合并要求

- 从 v1.1 Full Source **增量合并** P1.5/P2.5 文件，不覆盖用户已验证的 Windows 前端和既有 M1 数据库/事务实现。
- 只新增实验脚本、测试、候选前端浏览器测试及 CI 测试命令，正式业务 API 和 DB 迁移没有修改。
- 现有 CI 的 MySQL 测试环境必须确认为 `hospital_test`，测试夹具具备破坏性。
- 本次不发起真实患者数据流转、付费 AI 调用、真实发布或任何远程 Git push。
