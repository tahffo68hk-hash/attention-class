# Ward Map — 参数化建筑空间与交互调度沙盘 V1

状态：**CODE CANDIDATE / WINDOWS VISUAL GATE PENDING**。本报告基于此前交付的 V1 后端 + Product UIUX 候选 + WebGL Transition Follow-up 候选。**无法访问 Windows `E:\Attention is all you need`，也无法验证其 HEAD `9953835` 以后的真实改动。**

## 实际代码变更

- `frontend/src/modules/ward-map/scene-layout.ts`：布局与 Three.js 渲染解耦。每栋楼按病区归属、楼层和房间编号自然排序；**所有楼层共用同一建筑宽度、走廊轴线、双侧病房模块和层高**。房间沿中央走廊两侧镜像布置，床位按床号排序，每间三列且保持统一前后间距。房门朝向中央走廊。直接忽略后端 `simulated_position` 的旧散点定位（这些坐标也不是 BIM）。
- `frontend/src/components/WardScene3D.vue`：沿参数化布局创建楼板、中央走廊、病房隔断和门洞；床位按南北病房旋转，使床头朝向外侧墙体。继续保留 Hover V3 床位浮起、固定拾取体、五态颜色、透明遮挡、楼层切换和选中保持；模拟候选青色轮廓、当前模拟匹配金色轮廓、What-if 临时停用灰色轮廓，**真实床位主状态色不被覆盖**。
- `backend/app/api/v1/ward_sandbox.py`：新增 `POST /api/v1/ward-map/simulate`，仅 `ADMIN`/`NURSE` 可调用；明确要求 `scenario_kind=SYNTHETIC_ONLY`，拒绝附带姓名、诊断等额外字段。
- `backend/app/services/ward_sandbox.py`：完全只读加载 `Bed`/`Department`，在脱离 ORM 状态管理的临时快照上施加 What-if 假设，直接调用原有 `bed_policy.hard_constraint_violations`、`recommendation._score_*` 与 `WEIGHTS`、`global_optimization.greedy/optimize(backend='flow')`。没有 ORM 写入、没有临床患者创建、没有新的优化目标；`proven_optimal` 只使用真实求解器返回值。
- `frontend/src/components/WardSimulationPanel.vue`：新增沙盘开关、虚构申请、优先级/性别/隔离条件、单床临时停用、病房供给缩减、Greedy/精确优化切换、指标、候选评分、方案床位定位。参数变化后自动重新发起只读求解；异步结果按 epoch 丢弃过期响应。演示 SVG/假数据模式中不偷偷调用真实数据库或模拟「计算成功」。
- `frontend/src/views/WardMapView.vue`：沙盘结果与 3D、二维床位列表、点击抽屉联动；刷新实际业务快照时退出沙盘，避免旧结果继续当真。

## 几何计算和身份映射

- 建筑键：`building`；楼层键：`building·floor`；房间键：现有 `ward_id`；床位键：现有 `bed.id`。
- 同一病房的床位按床号及 ID 排序，摆放到同一个房间；房间有统一长宽、面向中央走廊的门洞和成排床位。
- 楼层高度 `4.9` 展示单位、病房宽 `12.2`、中央走廊宽 `4.5`；仅为**模拟布局比例**，不是米或医院测量数据。
- 从原始未筛选业务快照建立布局。筛选只影响物体显隐和 Raycaster，不影响空间坐标。楼层展开只做高度变换。

## 沙盘能力 / 实际边界

已实现：完全虚构请求（最多 30 条）、单患者候选与五维分项、Greedy/最小费用流联合匹配、单床假设不可用、病房供给减少、二维与 3D 匹配轮廓、结果定位、一键退出。

限定：原精确优化器目前单次最多 100 **候选**床位、2000 边；若源数据规模超过引擎边界，应返回明确输入错误而不是截断后宣称最优。What-if 目前只对**临时不可用**和**现有病房供给减少**做模拟，没有修改真实患者隔离属性、床位真实 status 或创建住院证。请求从 Web UI 生成虚构参数，服务端拒绝接收姓名/证件/诊断。

**真实性**：场景中的床位身份和状态来自只读业务快照；建筑几何是演示空间；沙盘是依据当前快照的计算结果，不是实时承诺。若实际业务数据变化，须重新计算。所有正式分配、入住、换床仍通过原业务 API 完成。

## 真实执行的测试

- Python 已运行：`PYTHONPATH=backend pytest -q backend/tests_ward_map backend/tests_m1_local backend/tests_p1p2 backend/tests_p15 backend/tests_p25 backend/tests_p3 backend/tests_p4`，**122/122 PASS**。
- 新增沙盘测试 **8/8 PASS**：权限、硬约束、分数与正式 `recommend_beds` 同源一致性、What-if、零业务写入、额外患者字段拒绝。
- `node frontend/verify_spatial_simulation.cjs` **PASS**：44 张合成床位、3 层楼、稳定映射、双侧病房、走廊留空、床位不碰墙及不重叠、各楼层建筑轴线一致。
- 原 V2 布局、V3 Hover 与 UI 产品离线守卫全部通过，改动 Vue SFC 脚本经 TypeScript transpileModule **无语法错误**。
- npm `--offline` 安装因 `@playwright/test` 不在缓存中失败，当前环境无 `vue/vue-tsc/vite/three` node_modules。**真实 vue-tsc、Vite build、Chromium/WebGL、帧率、Before/After 截图、真实 Windows/MySQL 回归：未验证**。

## Windows 正式项目集成清单

1. 获取最新 Git HEAD；先保存最新真实 WebGL **Before** 截图。检查是否已有同等沙盘能力；勿回放旧 ZIP。
2. 按 `BASELINE_SHA256.json` 比对每个文件的 base/patched SHA256，若当前文件不匹配，按 `SPATIAL_SANDBOX.patch` 的**语义增量**合并，不覆盖 Windows `WardScene3D.vue`。保留 `9953835` 之后的动画修复。
3. 运行 `vue-tsc --noEmit`、`vite build` 与新增测试；登录本地业务后验证 `POST /ward-map/simulate` 具备权限控制，拒绝额外患者字段。禁用/缩减供给不触发分配写入。
4. Chromium 真实 WebGL：44 张合成床位的空间布局、楼层轴线、Hover/Click、五态、遮挡恢复、方案高亮、快速切换 100 次；保存 Before/After、3D 沙盘截图。验证无控制台 JS 错误。
5. MySQL 只在隔离 `hospital_test` 执行现有测试，避免业务库破坏性操作。若数据实际数量/楼层不同，以 API 为准，测试不伪造床位。
6. 本地提交，**NO PUSH**。仅所有布局、业务隔离、三维交互、沙盘与浏览器 Gate 均通过后，才声明 `WARD_MAP_SPATIAL_SIMULATION_V1=PASS`。

当前判定：`SPATIAL_CODE_TESTS=PASS`，`SANDBOX_LOGIC_TESTS=PASS`，`WINDOWS_WEBGL_GATE=PENDING`，`WARD_MAP_SPATIAL_SIMULATION_V1=NOT_YET_VERIFIED`。
