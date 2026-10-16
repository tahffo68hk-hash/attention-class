# Attention is all you need — Ward Map 3D Editor V2 缺口关闭候选

## 基线和真实性边界

- 实现基线：已归档的 Spatial Simulation V1 Full Candidate + Editor V2 Partial Candidate。隔离 Git 基线 `cb45c5d`，**并非 Windows E: 最新仓库**。WorkBuddy 上一次报告 Windows HEAD `a6c75d2`，本环境无法独立核实它。
- 本轮不会更改 Windows 演示库、不会运行迁移、不会推送、不会调用 DeepSeek。
- 交付包为**可语义合并的真实代码候选**。不能将局部 SQLite / TS runtime 结果等同正式 MySQL + WebGL Gate。

## P0: 真实床与模拟床统一槽位

- `editor.ts` 的初始草稿同时包含真实床（持久化 scene_slot 或确定性回填）与负 ID 虚构床。
- `validatePose` 使用整份 EditorState 检查同病房冲突；不允许草稿床与真实床视觉叠床。
- `scene-layout.ts` 显式优先使用稳定位置/旋转，而不是每次按当前床位数量重新洗牌。
- 房间默认 12 个模拟展示槽位。房间满额时明确拒绝新增，避免自动扩大几何尺寸时移动已有床位；超过 12 床的历史房间按实际容量维持既有规模。
- `initialEditor`、`undo/redo`、真实供给减少的 `supplyDelta` 均可测试；模拟编辑不更改 SQLAlchemy 对象。

## P1: Three.js 空间编辑

- `WardScene3D.vue` 增加 `select/add/move` 编辑工具、由相机射线与楼层平面求交的网格吸附、独立半透明床位 Ghost（绿色合法/红色非法）、鼠标按下/拖动/松开事件。
- Ghost 不进入 `pickTargets`，不会与正常床位抢占 Raycaster。模拟床位仍使用负 ID，Hover/Click 与既有床位状态映射保持分离。
- 预览/选中床与局部遮挡 cutaway 联动；移出、重建和卸载释放 Ghost / 材质资源。编辑时禁用会冲突的 OrbitControls 平移。
- `WardBedEditor.vue` 实现工具栏、拖放落点、合法槽位、旋转、撤销/重做、模拟删除、重置。草稿仅存在当前页面内存，刷新后不保存。

## P2: 真实算法的模拟供给增减

- `POST /api/v1/ward-map/simulate` 追加 `synthetic_beds[]`（最多 20 张，负数 virtual_id、同病房真实 template_bed_id），仍为 `SYNTHETIC_ONLY`、只读。
- 虚拟床沿用同病房床模板的床型、性别限制、隔离属性、日费率、**用于评分的院内业务距离坐标**；这些是模拟代理值，绝不是 3D 展示坐标或真实新床实际测绘结果。
- 现有 Greedy / exact_min_cost_flow 要求候选床位 ID 为正整数：服务端将负 ID 映射到私有正整数求解器 ID，返回前还原负 ID。虚拟 ID 从不进入正式床位/分配写入。
- 编辑器模拟移除真实**空闲**床时仅将其加入临时 unavailable 集合；真实 Bed、BedAllocation、AdmissionRequest、AuditLog 无修改。
- `WardSimulationPanel.vue` 可以与编辑草稿一起启动，明确展示供给增减，点击重新计算使用新请求快照。算法与 H1–H4 / 原五维分项函数不变。

## P1: 正式管理（数据库变更，需 Windows test 库先验收）

- 新 Alembic `20261015ed02`：`beds.retired_at`, `beds.retired_reason`, `bed_scene_slots(bed_id,ward_id,slot,rotation)`，床号/床位唯一、病房槽位唯一；迁移回填历史床展示槽位，原有评分 `position_x/position_y` 无变化。
- 管理员 `POST /ward-map/managed-beds` 正式新增（明确确认、复用同病房模板生成初始评分坐标、状态固定 AVAILABLE）；`PUT /{id}/pose` 更新展示槽位；`POST /{id}/archive` 软停用；`POST /{id}/restore` 恢复；`GET /archived` 获取历史停用床。
- 正式停用仅允许 AVAILABLE / MAINTENANCE，且不得有 RESERVED / ADMITTED 活动分配；CLEANING 等必须经过正常流程。审核、事务和审计与正式 API 同一提交。`BedSceneSlot` 归档后保留原槽位，确保恢复时不会凭空搬床。
- 推荐、全局优化预览、真实分配硬约束、沙盘、Ward Map、床位管理列表、看板统计对已停用床做必要过滤；按 bed_id 查询历史分配和流水保持原语义。
- Existing `POST /beds` 也添加确定性展示槽位分配，避免绕过新管理路由产生“真实床没有位置”。
- 前端新增管理员专用 `WardBedManager.vue`，保存必须人工确认，成功后刷新。演示模式不会显示正式管理入口。

### 不改变的核心业务

- 不修改五维评分公式、H1–H4 规则、贪心/精确最小费用流目标函数、原分配状态机、原预占/换床事务。
- 不物理删除床位及历史分配；所有新增/停用/恢复必须后端核验权限并记录审计。
- 不是完整 BIM，不输出真实病房距离或临床建议。

## 当前运行证据（隔离容器）

| 项目 | 实测 |
| --- | --- |
| `pytest backend/tests_ward_map` | **22/22 PASS**（含新管理 6 项、迁移 SQLite 独立演练 1 项） |
| `verify_ward_editor_next.cjs` | **30/30 PASS**（纯逻辑 + Three.js 编辑契约静态） |
| 旧 Editor 守卫 | 18/18 PASS |
| Hover V3 | 9/9 PASS |
| Product Polish | 16/16 PASS |
| Spatial & V2 | 44 床 / 3 层确定性布局 PASS |
| `tsc --noEmit --strict` | 纯 TS 编辑器/空间/沙盘/类型模块 PASS |
| Vue script AST | 5 个文件语法 PASS（非 vue-tsc） |
| Python compileall | PASS |
| MySQL dialect BedSceneSlot DDL compile | PASS（非实际迁移） |
| OpenAPI | 44 paths |
| 既有 MySQL `tests/` | **BLOCKED**：本环境缺 `pymysql` 与独立 MySQL 实例；55 项在数据库 fixture 初始化时错误，不能称为业务测试通过 |
| vue-tsc + Vite Build | **NOT RUN**：容器没有 Vue/Three/npm 项目依赖 |
| 真实 Chromium Three.js WebGL、拖拽、两角度遮挡 | **NOT RUN**；未提供伪造截图 |
| 真实 MySQL 迁移/并发、Windows 演示库 | **NOT RUN**；禁止在未验收前执行演示库迁移 |

## Windows 集成顺序（不盲目覆盖）

1. 检查最新 Git HEAD、现有 `WardScene3D.vue`/`WardMapView.vue`，保留当前功能；用 `BASELINE_SHA256.json` 与 `IMPLEMENTATION.patch` 提取语义差异，特别 `WardScene3D.vue` 必须三方逐处合并。
2. 不在 demo/production 运行迁移！先在**独立 `hospital_test`** 备份并执行 Alembic，验证已有床位坐标/历史不变和 slot 回填，重复床号、槽位冲突、并发创建/预占、归档/恢复；本轮迁移测试只能运行在可确认的测试库。
3. 完成对应服务/Schema/API 合并和核心回归；实际 API 能正确执行前，不开放 UI 的正式管理按钮。不得将 `scene_slot` 写入业务评分 `position_x/y`。
4. 安装已有依赖运行 `vue-tsc`、Vite build；Chromium 真 WebGL 验证 Ghost 拖拽、编辑撤销、两视角局部 cutaway、五态 Hover、真实床与草稿床冲突，执行新 e2e（使用合成演示账号）。
5. 通过隔离 MySQL gate 后，再由用户手工授权演示库备份/迁移及正式操作；绝不可让自动化测试写演示库历史。
6. 保存真实 Before/After；只对实际变更运行必要回归；local git commit，NO PUSH。

## 仍然存在的限制

- 不能从本会话直接修改用户 Windows `E:` 工作区、读取最新 HEAD 或运行 Windows 本机 WebGL/MySQL。
- 只读草稿刷新不保存；没有跨会话的模拟方案持久化。
- 正式管理虽然有可运行的 ORM/HTTP 候选和 SQLite 证据，但 **未完成 MySQL 锁竞态和真实浏览器 Gate**，故不得称为生产可用。
- 新床沿用同病房模板的距离评分坐标仅供课程原型；实际医疗部署必须由医院确认新床数据。
- 独立场景 12 个槽位满额后阻止自动扩张；真正扩容需经明确的空间布局升级。

**当前状态：`WARD_MAP_3D_EDITOR_V2=NOT_YET_VERIFIED`，`CODE_CANDIDATE=READY_FOR_WINDOWS_GATE`。**
