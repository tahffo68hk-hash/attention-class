# 槽位式沙盘 V2 —— Windows 轻量集成报告

来源交付包：`Attention_Ward_Slot_Sandbox_V2_Minimal_Delta.zip`
（解包于 `E:\attention-handoff\Ward_Slot_Sandbox_V2_Minimal_Delta\`，**项目外**，未提交进仓库）

代码作者：ChatGPT。Windows 侧职责仅限**复制 / 语义合并 / 必要兼容修正 / 跑闸门 / 本地提交**，
未重新设计编辑器、未重做三方合并、未做无关全量审计。

集成分支基线：`54fc1b5`（`feat(ward-map): 集成三维编辑器 V2 Next`），分支 `main`。
本轮**保留全部未提交改动**，未 `git stash`、未 `git reset`、未整文件覆盖。

---

## 一、基线判定：哈希全部漂移 → 只做语义合并

`PATCH_MANIFEST.json` 自述 `patch_base` 为
"Archived Ward Editor V2 Next Delta 2026-10-15, **NOT user Windows HEAD**"。
对包内 3 个现有文件逐一比对 raw sha256 与 LF 归一 sha256，**全部不等于**包内 record
的 reference / candidate 哈希 —— 符合预期（本机已在此之上合入了 Hover V3、WebGL Transition
Follow-up、参数化布局与只读沙盘 V1）。

因此**未 `git apply`**，也未回退到任何旧包源码，而是逐段对照
`patches/INTEGRATE_EXISTING_FILES.patch`（340 行、3 个文件）只提取**功能语义变化**。

## 二、合并范围

**新增文件 3 个（原样复制，仅一处模块路径适配）**

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `frontend/src/modules/ward-map/slot-grid.ts` | 3.7 kB | 槽位几何**唯一**来源：`SLOT_COLUMNS/SLOT_X_STEP/SLOT_Z_STEP`、`slotCenter()`、`floorSlotCount()`、`listFloorSlots()`、`slotIntent()` |
| `frontend/src/components/WardSlotEditor.vue` | 10.7 kB | 工具条（查看 / ＋放置 / ↔移动 / −移除 / 撤销 / 重做 / 重置）+ 二维槽位按钮。**唯一改动**：模块引用改走 `@/` 别名（本仓路径约定），逻辑未动 |
| `frontend/verify_ward_slot_v2.cjs` | 5.8 kB | 19 项断言守卫 |

**现有文件 3 个（语义合并，非覆盖）**

| 文件 | 增 / 删 | 合并内容 |
| --- | --- | --- |
| `frontend/src/components/WardScene3D.vue` | +267 / −124 | 删除「平面求交反推槽位」整套（`placement` / `placePlane` / `placePoint` / `previewPlacement`），改为**真实瓦片射线拾取**；新增 `buildFloorSlots()`、`updateSlotVisibility()`、`pickSlot()`、`previewFloorSlot()`、`restoreSlotHover()`、`onEditContextMenu()` |
| `frontend/src/modules/ward-map/scene-layout.ts` | +13 / −16 | 删除本地镜像常量 `BED_PITCH_X/BED_INSET_X/BED_INSET_Z`，改为从 `slot-grid.ts` 转发 `BED_COLUMNS/BED_PITCH_Z`；床位落位统一走 `slotCenter()` |
| `frontend/src/views/WardMapView.vue` | +13 / −7 | 接入 `WardSlotEditor`、`editTool` 增 `'remove'`、`editorRef` 暴露、`@edit-cancel` 回传 |

**既有守卫 3 个（必要适配，否则误报失败）**

| 文件 | 原因 |
| --- | --- |
| `frontend/verify_ward_editor_next.cjs` | 原断言绑死 `raycaster.ray.intersectPlane`（该实现已被交付要求移除）→ 改为语义等价锚点组：`edit-place` / `pointerup` / `ensureGhost` / `intersectObjects(slotTargets` / `ghostMaterial.color.set` / `props.editorOccupied?.find` |
| `frontend/verify_v2_layout.cjs` | `scene-layout.ts` 现在运行时依赖 `slot-grid.ts`，Node 不解析 `.ts` 相对模块 → 补 `m.require` 转译加载器 |
| `frontend/verify_spatial_simulation.cjs` | 同上 |

## 三、语义合并要点

1. **几何单一来源**。槽位中心原由三处各自计算（床位落位、二维瓦片、Ghost 预览），常量
   `2.35 / 3.08 / 3.4 / 1.9` 各写一遍。合并后三者同源调用 `slotCenter(room, slot)`，
   漂移风险归零；`floorSlotCount()` 由房间进深派生，不再是写死数字。
2. **Ghost 合法性从「粗算」变「命中即所点」**。旧实现取射线与地面平面交点再反推最近槽位，
   点位与落点可能错开一格；新实现直接 `raycaster.intersectObjects(slotTargets, false)`。
   合法性**粗判**在场景层（`tile.userData.kind`：`empty / real / draft` → `#32B38C` / `#E35A60`），
   **终判**在编辑器面板（正式床 / 模拟床区分、移动源、容量），两层口径一致。
3. **工具态与取消**。`props.editTool: 'select'|'add'|'move'|'remove'`；画布右键
   `preventDefault` + 隐藏 Ghost + `emit('edit-cancel')`（`initialize()` 注册、
   `destroy()` 反注册 `contextmenu`）；Esc 由 `WardSlotEditor` 侧处理。
4. **场景生命周期**。`clearScene()` 追加 `restoreSlotHover()`、`slotTargets.length = 0`、
   `slotMaterials = null`、`slotLabelMaterials.clear()`；`rebuild()` 与
   `viewMode/focusFloor`、`[cutaway, editorMode, editTool, editRoomId]` 两个 watch 均补
   `updateSlotVisibility()`，避免切楼层后残留上一层的槽位瓦片。

## 四、本轮修正（4 处，均限定在集成兼容范围）

1. **槽位编号肉眼不可读（必要修正）**。交付版复用 `textLabel()` 的 768×176 画布贴到
   2.5 单位宽的四边形上，实际只剩 ~2px，截图放大仍是模糊色块 —— 而验收明确要求
   「截图必须能看见地面槽位编号」。新增专用 `slotLabelMaterial()`：192×96 画布、
   `700 76px "Microsoft YaHei"`、按文本缓存（`S01` 跨病房复用，避免每楼层数百张重复贴图），
   `slotLabelGeometry` 注册进 `sharedGeometries` 统一释放。
   修复后 `S09/S10/S11/S12` 在整页截图即可辨认。
2. **移动工具第二次点击失效（真实缺陷，最小修复）**。「↔ 移动」时点模拟床**自身所占据的槽位**
   会以同槽位触发 `edit-place` → 编辑器清空 `selectedId` → 再点目标槽位时已无源，
   表现是「点了目标槽位但床没动」。在 `pointerEnd` 增加 `selectingOnly` 判定：
   `editTool === 'move' && tileBedId !== null && tileBedId === sourceId` 时只选中、不落子（3 行）。
   **该缺陷属交付版逻辑，非合并引入**，已在本轮附带修好；建议同步回上游作者确认口径。
3. **`verify_ward_slot_v2.cjs` 源码正则过严**。交付断言写成压缩风格
   （`editorActive?editorState:null`），本仓 Prettier 格式化后带空格 → 误报 18/19。
   三处源码正则改为容忍 `\s*`，文件头加 `[LOCAL ADAPTATION]` 说明；**19 项运行时断言原样保留**。
4. **既有守卫取不到跨 `.ts` 依赖**。见 §二 表，两处补加载器。

另：本轮曾插入临时只读探针（`[DEBUG-PROBE-V6]` / `probeSlot` / `window.__wmSlot`）用于
确定槽位→屏幕坐标映射，**验完已全部删除**（`grep -c` = 0），随后复跑全部闸门。

## 五、闸门结果（全部本轮实测）

| 闸门 | 结果 |
| --- | --- |
| `verify_ward_slot_v2.cjs` | **19/19 PASS** |
| `verify_ward_editor_next.cjs` | **30/30 PASS** |
| `verify_ward_editor.cjs` | **23/23 PASS** |
| `verify_hover_visual.cjs` | **10/10 PASS** |
| `verify_reduced_motion_parity.cjs` | **12/12 PASS** |
| `verify_webgl_transition_guards.cjs` | **17/17 PASS** |
| `verify_v2_layout.cjs` | **V2_LAYOUT_GATE PASS**（44 床 / 3 层 / 位置稳定 / 映射完整） |
| `verify_spatial_simulation.cjs` | **SPATIAL_LAYOUT PASS** + **SANDBOX_CONTRACT_TS PASS** |
| `vue-tsc --noEmit` | exit 0（0 错误） |
| `vite build` | `✓ built in 4.51s`（仅既有 chunk >500 kB 告警，`WardMapView` 619.85 kB，属 three.js 历史情况） |
| 后端（无代码改动，回归 1 项） | `tests_ward_map/test_ward_editor.py::test_synthetic_supply_uses_exact_solver_and_never_writes` **1 passed** |

本轮改动**全部在前端**（`git diff --numstat` 无后端条目），因此未重跑 87 项后端全量套件。

## 六、真实 Chromium WebGL 验收

环境：本机 Vite dev server `127.0.0.1:5173` + 真实 Chrome（headless，`agent-browser`），
后端 `127.0.0.1:8000`。证据存 `docs/screenshots/v6_*.png`（13 张，覆盖 8 类行为，非逐帧冗余）。

| 验收项 | 实测结果 | 证据 |
| --- | --- | --- |
| 地面固定槽位渲染 | 101 病房 **12 个槽位** `S01–S12`，编号肉眼可读；`S01–S08` 正式占用 / `S09–S12` 空槽；统计`44 正式床 · 0 模拟床 · 当前病房 4 空槽` | `v6_01_floor_slots.png`、`v6_03_slot_numbers_zoom.png` |
| 单层聚焦 | 聚焦层槽位随楼层重建，位置与床位一致 | `v6_02_focus_floor.png` |
| 绿 Ghost（合法落点） | 悬停空槽 `S10` 出现半透明绿 Ghost，落位与槽位编号对齐 | `v6_04_ghost_green_S10.png` |
| 放置 | 点击后 → `44 正式床 · 1 模拟床 · 当前病房 3 空槽`，`S11` 转「模拟」态 | `v6_05_placed_S10.png` |
| **正式床拒绝移除** | 「− 移除」点正式床 → 红字 `正式床位不能在模拟沙盘中直接删除；请使用 What-if 临时禁用`，计数**未变**（44 / 0），**未发任何正式 DELETE** | `v6_06_remove_real_rejected.png`、`v6_06b_remove_rejected_text.png` |
| 移动 | 「↔ 移动」`S11`（模拟）→ `S12`（空），`S11E / S12D`，模拟床数仍为 1 | `v6_07_moved_to_S12.png` |
| 撤销 / 重做 / 重置 | 移除后 `0 模拟床` → 撤销 `1 模拟床` → 重做 `0 模拟床` | `v6_08_undo_redo.png` |
| 楼层切换 | 切 2F 后标题 `模拟住院楼 · 2F 14床`，槽位仍 12 个（`.slot-tile` 计数 = 12） | `v6_09_floor_switch.png` |
| 真实快照下的草稿 | 非演示数据下草稿落 `S05`，计数 `总床位 45` | `v6_10_live_draft.png` |
| 沙盘供给走既有优化 API | 面板显示 `编辑器供给变化：模拟新增 1 张，临时移除空闲床 0 张`，候选清单含 `SIM-001`；**未新增任何评分实现** | `v6_11_supply_sandbox.png` |
| 退出回真实态 | 退出沙盘 / 退出编辑后回到 `44` 床，页面不再含 `SIM-` | `v6_12_back_to_live.png` |
| Hover V3 未回退 | 悬停 101-06 提示 `● 空闲 心内科 · 101 病房 暂无活动分配记录 点击床位查看详情与状态流水` | 同上轮 `v3_*` 口径，本轮复验一致 |

合成床 id 恒为负（`Math.min(0,…)−1`），不进入任何业务接口；除「沙盘供给」按钮走**既有**
优化接口外，编辑器全程零业务写入。

## 七、未完成 / 环境限制（如实记录）

1. **演示库 `hospital` 未迁移**（既有阻塞项，非本轮引入）：缺 `bed_scene_slots` 表。
   在进程内用当前源码直连演示库会报
   `Table 'hospital.bed_scene_slots' doesn't exist`（500）。故浏览器验收的数据源与
   上轮一致为 `SYNTHETIC_DEMO`，真实库侧行为由后端测试证明。
2. **运行中的 8000 端口后端是旧进程**：`POST /api/v1/ward-map/simulate` 带
   `synthetic_beds` 返回 **422 extra_forbidden**（旧进程不认识新字段）。未重启用户的服务；
   沙盘供给链路由 `test_synthetic_supply_uses_exact_solver_and_never_writes` 证明
   （`optimized.admitted == 2` 且 `proven_optimal`、含负 id 的合成床配对、
   写入前后四张表计数一致、`not session.dirty and not session.new`）。
3. **沙盘「重新计算模拟方案」在 headless 下未跑出结果**：按钮
   `:disabled="!patients.length || busy || !available"`，headless 下科室 `<select>`
   未能成功选中导致 `patients` 为空。**未修改产品代码**（改测试环境不改产品），
   改由上述后端测试覆盖同一接口。
4. **未做**：Alembic 迁移（本轮无 schema 变化）、后端全量 87 项重跑、旧包三方合并、无关审计。

## 八、提交

本地提交，**NO PUSH**。提交前已扫敏感信息：本包无凭据、无密钥、无真实患者数据，
仅前端源码、守卫脚本与截图。
