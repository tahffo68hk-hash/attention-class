# Ward Map 3D Editor V2 Next —— Windows 侧集成报告

来源交付包：`Attention_Ward_Map_Editor_V2_Next_Delta_20261015.zip`
（候选仓基线 `cb45c5d`，声明 Windows 正式仓 HEAD 为 `a6c75d2`，**非相同源码基线**）

集成方式：**逐文件哈希比对 + 反向还原候选基线 + 真三方合并**，未整包覆盖、未 `git apply`。
基线不是本机，因此先用 `IMPLEMENTATION.patch` 反向还原出候选真基线（LF 归一后 19/19
与 `BASELINE_SHA256.json` 一致，基线可信），再以「本机 / 候选基线 / 候选补丁」三方合并。
29 个变更文件中 20 个干净合入、9 个逐 hunk 人工合并（`WardScene3D.vue` 与 `WardMapView.vue`
结构漂移最大，均为逐处并入）。

---

## 一、闸门结果（全部实测）

| 闸门 | 结果 |
| --- | --- |
| `python -m compileall app tests tests_ward_map alembic` | 通过 |
| OpenAPI 路径 | **44**（基线 39，新增 5 条 `ward-map/managed-beds*`） |
| `pytest -q tests tests_ward_map` | **87 passed**（基线 79，新增 8 项见下） |
| 7 个前端离线守卫 | 全绿：`ward_editor_next` 30/30、`ward_editor` 23/23、`hover_visual` 10/10、`reduced_motion_parity` 12/12、`webgl_transition_guards` 17/17、`v2_layout` PASS、`spatial_simulation` PASS |
| `vue-tsc --noEmit` | exit 0 |
| `vite build` | 通过（5.66s；仅 `WardMapView` 分包 615kB 的体积告警，属 three.js 既有情况） |
| Alembic 迁移链 | 单一 head `20261015ed02`（`9bca1026e001 → 20261015ed02`） |
| 测试库从零迁移 | `hospital_test` 每次会话 `DROP ALL + alembic upgrade head` 后跑通全部 87 项 |

## 二、真实 Chromium WebGL 验收（编辑器）

环境：本机 Vite dev server 5173 + 真实 Chrome 153（headless，`agent-browser`）。
数据源：**合成演示数据（SYNTHETIC_DEMO）**——原因见 §四.2，演示库未迁移。

| 验收项 | 实测证据 |
| --- | --- |
| 登录 → 态势图页面 | 登录跳转 `/dashboard`；`/ward-map` 渲染出 `926×520` WebGL canvas，44 张床、五态统计（空闲 21 / 预占用 7 / 已入住 8 / 清洁中 5 / 维护中 3）——`v5_02_demo_3d.png` |
| 五态 hover 未回归 | hover 探针在画布 49 点扫描中同时读到 **空闲 / 预占用 / 已入住 / 清洁中 / 维护中** 五种徽标文案 |
| 编辑器打开 | 面板（`.wm-editor`）控件齐全：病房 6 / 槽位 12 / 朝向 4 / 虚构床号；工具 `选择 · ＋添加/预览 · 拖动已选床`——`v5_03_editor_open.png` |
| 模拟编辑与只读沙盘互斥、演示模式隐藏正式管理入口 | 演示模式下工具栏仅 `模拟编辑 · 二维列表 · 重置视角`，"⚙ 床位管理"不出现 |
| **Ghost 落点预览（绿=合法 / 红=不可放置）** | 48 点扫描：3 点判 **GREEN**（槽位 8/9/11，正是 101 病房的 3 个空闲槽）、5 点判 **RED**（1–8 已占用槽）、40 点判 NONE（房外，Ghost 隐藏）。合法点截图中可见 `#32B38C` 半透明落点——`v5_04_ghost_green_free_slot.png`（中心 13×13 均值 `r−g = −38.6`，绿主导） |
| **拖放落子（pointerdown→move→pointerup）** | Ghost 判定 `valid=true` 且位移 > 5px 时落子：床位总数 **44 → 45**，槽位 9 转为「已占用」；`撤销` 后回到 **44** |
| 按选定槽位添加 | 表单选槽 9 + 床号 `SIM-E2E-001` → 总数 **44 → 45**；`撤销` → **44**——`v5_08_draft_added.png` |
| 旋转 | 选中 101-05 后 `R · 旋转 90°`：朝向 **0° → 90°** |
| 从模拟场景移除 | 选中间隙床后移除：总数 **44 → 43**；`撤销` → **44** |
| 控制台 | 无 page error；`console` 仅 Vite 连接日志 |

合成床 id 恒为负数（`Math.min(0,…)−1`），未进入任何业务接口；编辑器全程零业务写入。

## 三、正式床位管理接口（真实 MySQL `hospital_test` 3307）

新增 `backend/tests/test_ward_editor_mysql.py`（8 项，**真实 MySQL**）。之所以另开一份：
`tests_ward_map/test_ward_editor.py` 跑在 SQLite，其 docstring 自己写明
"MySQL row-lock races must be retested in hospital_test"。

| 用例 | 覆盖 |
| --- | --- |
| `test_lifecycle_and_audit_on_mysql` | 新增 201 → **幂等重放同 id 且床数 +1**；审计与业务同事务；展示槽位不污染 `position_x/position_y`；停用后从态势图消失、恢复后重新出现且 **槽位不变** |
| `test_archive_denied_for_non_free_status_on_mysql` | `RESERVED/OCCUPIED/CLEANING` 一律 `409 ILLEGAL_STATE_TRANSITION`，且 `retired_at` 保持 `None` |
| `test_slot_conflict_is_rejected_without_partial_write` | 跨床位抢同一槽位 → 409；**B 槽位未变、槽位行数未变、无半成品写入**；换空闲槽位成功且评分坐标不变 |
| `test_concurrent_create_same_slot_serializes_via_row_lock` | 双线程 barrier 同抢同一病房槽位 6 → **恰好 1 成功、1 被拒**（`ConflictError`/`IntegrityError`），最终该 `(ward, slot)` 只有 1 行、床位只 +1 —— 验证 `SELECT … FOR UPDATE` + `uq_bed_scene_ward_slot` |
| `test_non_admin_cannot_touch_managed_beds`（×3 角色） | 未登录 401；`nurse/doctor/viewer` 一律 **403 PERMISSION_DENIED** 且**不写库**、但**留审计痕迹** |
| `test_admin_can_create_and_unknown_bed_is_404` | ADMIN 201；不存在床位 `404 NOT_FOUND` |

## 四、本轮发现并修复的缺陷

1. **`backend/tests/conftest.py` 的 `TABLES` 截断清单缺少新表 `bed_scene_slots`**（真实缺陷）。
   该表随本次迁移新增，若不截断会在用例间残留脏槽位，使 `_slot_free` 误判「槽位已占用」，
   并让「同病房槽位唯一」断言失真。已补入清单。
2. **`frontend/verify_ward_editor.cjs` 对合成床负 id 的断言是「写法级」的**（真实缺陷）。
   原断言 `/id:\s*-1-/` 绑定旧写法 `-1-Math.max(...)`；本候选改用
   `Math.min(0,…)-1`，语义等价但写法变了 → 断言误报失败。已改为**运行时断言**
   （所有 `synthetic` 草稿床 id 恒 < 0），守住真正的不变量。

## 五、已知偏差与未完成（如实记录）

1. **演示库 `hospital` 未迁移**。交接要求「迁移只能先在 `hospital_test`，再由用户手工授权演示库」，
   故本轮**未对演示库执行任何迁移**。后果：在演示库完成迁移前，新代码的后端不能接演示库
   （`beds.retired_at` 等列不存在，`GET /ward-map` 会失败）。这需要**用户授权**后单独执行
   （先备份，再 `alembic upgrade head`）。
2. **幂等重放的审计语义**：同一创建请求重放会**再写一条 CREATE 审计**（每个请求都留痕）。
   交付候选刻意如此，本轮**未改动**该行为，仅在此记录。
3. **Ghost 在已占用槽位时被不透明床体深度遮挡**：此时视觉上呈一块红色平面而非完整红色床体
   （`depthWrite:false` 但仍参与深度测试）。功能判定正确（valid=false），仅视觉饱满度不足。
4. **未做**（与交付包一致）：自由拖拽的手柄交互、草稿跨会话持久化、对虚拟床正式评分、
   真实 BIM/真实病房距离、正式管理入口在演示模式下开放。
5. **未执行 `push`**（按交接要求 NO PUSH）。

## 六、结论

`WARD_MAP_3D_EDITOR_V2_NEXT` 的**代码集成、真实 MySQL 事务/并发/权限、真实 Chromium WebGL
编辑器烟测**均已完成并通过。剩余唯一阻塞项是**演示库迁移需用户授权**。
