# 病区床位态势图 · 三维模拟空间编辑器 V2 集成报告

- 交付包：`Attention_Ward_Map_Editor_V2_Partial_Candidate.zip`
- 基线（合并前 HEAD）：`b7a747d`　feat(ward-map): 集成参数化空间布局与只读调度沙盘 V1
- 合入方式：**语义增量合并**（逐 hunk 手工并入），未整体覆盖、未 `git apply`
- 推送状态：**未 push**（本地提交）

---

## 0. 一句话结论

交付包是**自述为「部分完成、未充分验证」**的候选件。经哈希核对、三方合并、断网闸门与真实 Chromium 验收后判定：
**功能可用、边界自洽、真实数据零污染，可以合入**；其自述的「未实现/未验证」项在合并报告中**照原样保留**，不得当成已交付能力。

---

## 1. 交付件核对

### 1.1 完整性（交付件 → 自身声明的哈希）

包内 8 个条目，其中 6 个代码/文档文件与 `EDITOR_V2_SHA256.json` 逐一比对，**全部一致，无篡改**：

| 文件 | 声明哈希（前缀） | 核对 |
| --- | --- | --- |
| `frontend/src/modules/ward-map/scene-layout.ts` | `74f55e16…` | ✅ |
| `frontend/src/modules/ward-map/editor.ts` | `9547a0a5…` | ✅ |
| `frontend/src/components/WardScene3D.vue` | `2fecad42…` | ✅ |
| `frontend/src/components/WardBedEditor.vue` | `e1347f55…` | ✅ |
| `frontend/src/views/WardMapView.vue` | `03642b1c…` | ✅ |
| `frontend/verify_ward_editor.cjs` | `b5625e32…` | ✅ |
| `docs/WARD_MAP_3D_EDITOR_V2.md`（清单原文） | `a75a9a40…` | ✅ |

### 1.2 基线漂移

| 文件 | 与本仓库现状 | 处理 |
| --- | --- | --- |
| `WardScene3D.vue` | 双方都改过 | 三方合并 |
| `WardMapView.vue` | 双方都改过 | 三方合并 |
| `scene-layout.ts` | 双方都改过 | 三方合并 |
| `editor.ts` | 本仓库没有 | 新增 |
| `WardBedEditor.vue` | 本仓库没有 | 新增（本地化适配） |
| `verify_ward_editor.cjs` | 本仓库没有 | 新增（本地化 + 加固） |
| `WARD_MAP_3D_EDITOR_V2.md` | 本仓库没有 | 新增（原文归档，供复核） |

**基线确实是「旧」的**：交付包基于归档的 `Attention_Ward_Map_Spatial_Simulation_V1_Full_Candidate_20261015.zip`，不是活的 Windows 工作树 —— 与它自己的 Integration 说明一致。

### 1.3 关键一步：找到了精确合并基点

本项目此前吸收过 `Ward_Map_Spatial_Simulation_V1_Delta_20261015`，其 `PATCHED_FILES/` 目录与本交付包的共同祖先只差
**`WardScene3D.vue` +15/−5、`WardMapView.vue` +17/−6、`scene-layout.ts` +4/−3 行**。
因此本次可以做**真三方合并**：编辑器相关的 hunk 全部从这组差分里**提取**，而不是靠手写猜。

---

## 2. 合并明细

最终改动：**4 改 + 3 新增源码 + 1 归档文档 + 9 张验收截图**

```
 frontend/src/components/WardScene3D.vue       | 41 +++++++++++--
 frontend/src/modules/ward-map/scene-layout.ts | 22 +++++--
 frontend/src/modules/ward-map/ward-map.css    | 88 +++++++++++++++++++++++++++
 frontend/src/views/WardMapView.vue            | 78 +++++++++++++++++++++++-
 4 files changed, 217 insertions(+), 12 deletions(-)
```

### 2.1 `WardScene3D.vue`（8 个 hunk，+41/−6）

- 新增 props：`editorMode?`、`cutaway?`、`editorPoses?`（床位 id → 病房/槽位/旋转）
- 新增 emit：`edit-select`
- `rebuild()`：`createHospitalPlan(props.rooms, props.beds, props.editorPoses)`
- `click()`：编辑态改发 `edit-select`（**不触发**真实床位管理）
- `pointerMove()`：编辑态光标 `crosshair`
- `updateOcclusionTargets()` 追加**编辑态局部剖切**：只淡化目标病房邻域（同层、同高度带）的构件
- 监听器 `[beds, rooms]` → `[beds, rooms, editorPoses]`；新增 `[cutaway, editorMode]` 触发器

> 红线守住：原有 raycast 悬停/选中、楼层与状态映射**全部保留**，剖切只是叠加一层淡化。

### 2.2 `scene-layout.ts`（保留本地版，新增 `poses` 形参）

交付版是 66 行压缩稿，本地版是 202 行带注释的格式稿，**导出面完全相同**。因此保留本地版，只把「姿态」能力并进来：
按 `poses[bed.id]` 取槽位与旋转（`slot` / `rotation`），缺省时退回按床号顺排 —— 老行为不变。
文件头补充契约说明：`poses` **仅用于显示，永不回写、永不参与评分**。

### 2.3 `WardMapView.vue`（+78）

- `allBeds` 拆成 `realBeds`（真实快照）与 `allBeds`（编辑态下改为“真实 + 模拟”）
- 新增 `editorActive` / `editorState` / `editorPoses` / `enterEditor` / `exitEditor` / `editorUpdate`
- `load()` 与 `setDemo()` 都会 `exitEditor()`（切演示数据必须退回真实视图）
- `selectBed()` 增加**编辑态早退闸门**：不读、不取患者状态流水
- 工具栏新增首个按钮 `▦ 模拟编辑 ⇄ 退出模拟编辑`；原沙盘按钮在编辑态 `disabled`（两者互斥）
- 新增 `<WardBedEditor>`，并给 `<WardScene3D>` 挂 `editor-mode / cutaway / editor-poses`

### 2.4 新增文件

| 文件 | 说明 |
| --- | --- |
| `frontend/src/modules/ward-map/editor.ts` | 纯函数编辑模型（草稿增删改、校验、撤销/重做，历史栈上限 50 步） |
| `frontend/src/components/WardBedEditor.vue` | 编辑面板（无 `<style>` 块，样式落在全局 CSS） |
| `frontend/verify_ward_editor.cjs` | 断网自检脚本（交付 18 项 + 本地新增 5 项只读边界审计） |
| `docs/WARD_MAP_3D_EDITOR_V2.md` | 交付件清单**原文归档**（哈希 `a75a9a40…` 与声明一致），便于复核其自述边界 |

---

## 3. 为了能过闸，本地必须做的 5 处适配

交付件自述「未跑 `vue-tsc`/Vite build」，下列问题在本地闸门里全部暴露并已修正：

| # | 文件 | 问题 | 本地处理 |
| --- | --- | --- | --- |
| 1 | `editor.ts` | `TS6133: 'room' is declared but its value is never read`（本项目开了 `noUnusedParameters`） | 形参改名 `_room` |
| 2 | `editor.ts` | `TS2550: Property 'at' does not exist`（本项目 `target/lib = ES2020`，`Array.prototype.at` 需 ES2022） | 改为 `state.history[state.history.length - 1]!` |
| 3 | `WardBedEditor.vue` | 交付版带内联 `<style scoped>` 且**硬编码浅色**（`#f7fbff`/`#18384b`/`#d6e6ed`），在深色主题下会亮成一块补丁 | 移除 `<style>` 块，样式并入 `ward-map.css`，**只用全局令牌**（`--surface/--border/--muted/--primary-strong/--danger/--radius`）；按钮改用全局 `.btn / .btn--sm / .btn--primary` |
| 4 | `WardBedEditor.vue` | 交付版把 `state.items.length`（**全病房**草稿数）传给 `roomSlots`，而 `validatePose` 是**按本病房**判重 → 刚添加的床可能被判「病房不存在」 | 新增 `roomBedCount`（只数本病房）与 `slotOptions` computed，与 `validatePose` 口径对齐 |
| 5 | `verify_ward_editor.cjs` | 硬编码 Linux 路径 `/opt/nvm/.../typescript.js` | 改为 `require('typescript')`（配 `NODE_PATH`）；并**新增 5 项只读边界审计**：禁用 `fetch/axios/XMLHttpRequest`、禁用 `/ward-map/simulate` 与 `/beds/*/status|archive|restore`、合成 id 必须为负（`id: -1 - …`）、历史栈必须裁剪到 50 步 |

### 3.1 绕过的两个坑（记录以免复发）

- **`<Teleport>` 与设计令牌**：详情抽屉渲染到 `<body>`，`scoped` 样式管不到它，硬编码色在深色主题必然出错 —— 所以第 3 项不是「美化」，是**必需**。
- **`NODE_PATH`**：源码守卫用 `ts.transpileModule` + `Module._compile`，必须把 `NODE_PATH` 指向 `frontend/node_modules`，否则 `require('typescript')` 失败。

---

## 4. 闸门结果（全部本地实跑）

### 4.1 后端

| 闸门 | 结果 |
| --- | --- |
| `compileall app alembic` | exit 0 |
| OpenAPI 路径数 | **39**（与合并前一致 → 证实「本包不含后端改动」） |
| 路径存在性 | `ward-map: True`　`simulate: True` |
| `pytest -q tests tests_ward_map` | **72 passed**（主链 57 + 病区/沙盘 15），1 warning，58.53s |

> 测试库每次都由 `alembic upgrade head` 从零建表，因此这轮同时也在验证迁移脚本。

### 4.2 前端

| 闸门 | 结果 |
| --- | --- |
| `verify_spatial_simulation.cjs` | PASS（3 层、44 床唯一落位、0 重叠、走廊与墙体净距、刷新确定性） |
| `verify_v2_layout.cjs` | PASS（44 床、3 层、位置稳定、映射无缺失） |
| `verify_hover_visual.cjs` | **10/10 PASS** |
| `verify_webgl_transition_guards.cjs` | **17/17 PASS** |
| `verify_reduced_motion_parity.cjs` | **12/12 PASS** |
| `verify_ward_editor.cjs`（新增） | **23/23 PASS**（交付 18 项 + 本地 5 项边界审计） |
| `vue-tsc --noEmit` | exit **0** |
| `vite build` | ✅ 4.34s，`WardMapView-vGuDsAi5.js` **599.97 kB**（gzip 157.92 kB） |

---

## 5. 真实浏览器验收（Chromium / WebGL）

### 5.1 交互链（逐项实跑，控制台**零 error**，只有 vite 调试行）

| 动作 | 观测 |
| --- | --- |
| 点 `▦ 模拟编辑` | 面板出现；提示「仅修改模拟草稿，真实数据库没有变化」；病房下拉 12 项、槽位下拉 12 项 |
| 选病房 + 槽位 + 床号 `SIM-001` → 添加 | 场景床位总数 **44 → 45** |
| 重复槽位再加 | 被拒：**该槽位已有床位** |
| 撤销 / 重做 / 重置 | 提示「已恢复模拟快照」；床位总数回到 44 |
| 点 `退出模拟编辑` | 面板消失，回到真实快照 |
| 深/浅主题切换 | 面板与场景随之换肤，无硬编码亮色残留 |

### 5.2 决定性证据：投影定位法

前几轮尝试（3 代剖切隔离法）全部**作废**，原因各有不同（见 §5.4）。最终采用的方法把干扰源逐条掐掉：

1. **指针停在画布角落** → 不触发悬停提示浮层，也不触发编辑态剖切 ⇒ 画面只由「床位集合 + 相机」决定，完全确定；
2. **在页面内用当前相机把合成床位的世界坐标投影成画布相对坐标**（`getWorldPosition` → `project(camera)`），而不是靠猜它在屏幕哪里；
3. **只比对投影点邻域**（120×120 窗口），差异必须精确落在那里才算数。

页面内回读（`ward-scene-canvas` 组件 `setupState`，只读探针，不写任何状态）：

```
基线   ：selectableSize = 44，无负 id 床位
加草稿 ：selectableSize = 45，负 id 床位 world = [9.56, 14.7, 8.7]
         投影 rx = 0.432755，ry = 0.270955，inFrustum = true
移除后 ：selectableSize = 44，负 id 床位 = null
```

像素差分（裁剪到**各自帧**的画布矩形，规避编辑面板增高造成的 31px 位移）：

| 对比 | 投影点邻域差异 | 包围盒 | 最大通道差 |
| --- | --- | --- | --- |
| 基线 → 加草稿 | **324 px / 14400（2.25%）** | 40×28，居中于投影点 | 132 |
| 基线 → 移除后 | **0 px** | — | **0** |
| 加草稿 → 移除后 | **324 px** | 同一个包围盒 | 132 |

三联图证据：`docs/screenshots/v4_93_editor_draft_proof.png`
（① 基线红圈内是空地 → ② 加入 `SIM-001` 后红圈内出现一张独立床位 → ③ 移除后红圈恢复空地，与①无差异）

**结论**：模拟草稿床位确实被 Three.js 画出来了；且**移除后画面逐像素回到基线** —— 只读、可逆、对真实场景零残留。

### 5.3 只读性核验（真实 MySQL）

| 表 | 会话前 | 会话后 |
| --- | --- | --- |
| `beds` | 44 | **44** |
| `bed_allocations` | 23 | **23** |
| `admission_requests` | 22 | **22** |
| `audit_logs` | 274 | 286（**+12，全部是 `LOGIN / SUCCESS / admin`**） |

逐条核对最近审计：新增行**全部**是每次浏览器会话登录触发的一条 `LOGIN`（本就设计为必留痕），
**没有任何**床位状态、分配、住院证相关的写入。
复合只读契约：*编辑器改动 0 条业务写、0 条业务审计*。

### 5.4 作废的验收材料（已删除，避免误引）

本轮共 34 张新截图，删掉 **25 张**会误导的，只留 9 张真证据：

| 被删系列 | 为什么是误导 |
| --- | --- |
| `v4_40…v4_45`（3D 系列） | `find text 查看三维 click` 被 `<dt>` 遮挡 → 实际一直停在**二维列表**，其中 4 帧完全相同 |
| `v4_50…v4_53`（明暗往返） | 两组各自逐字节相同，差异恒为 0，会读成「什么都没变」 |
| `v4_60…v4_63`（剖切 1 代） | 探针与画面不同步，`62 == 63` |
| `v4_70…v4_73`（剖切 2 代） | 详情抽屉盖住画布，四张尺寸异常（80k/108k） |
| `v4_80…v4_83`（剖切 3 代） | 编辑面板增高 31px 使**固定裁剪坐标**失效，`82 == 83` |
| `v4_30/31/34` | 被 `v4_90` 投影法基线取代 |

留下 9 张：`v4_32`（编辑器打开）、`v4_33`（选病房）、`v4_35`（加草稿后）、
`v4_38`（浅色主题）、`v4_39`（退出后）、`v4_90/91/92`（投影法三态原图）、`v4_93`（三联证据图）。

---

## 6. 交付件自述的「未实现 / 未验证」（**原文照引，不得当成交付能力**）

> ### Explicitly NOT implemented / NOT VERIFIED
> - Free-form drag/drop and animated translucent insertion preview; the current editor is grid slot-based controls, not Minecraft-like dragging.
> - Formal DB create/archive/restore APIs, archive timestamp migration, idempotency, locking, audit and real MySQL concurrent tests. None are claimed; formal mode is NOT enabled. Do not try to translate negative synthetic IDs into official bed IDs.
> - Persisted drafts, dynamic preview sandbox scoring on added virtual beds, changes to existing `ward_sandbox` API, or authentic clinical workflow writes.
> - Full `vue-tsc` / Vite build, live Chromium WebGL or Windows E: repository integration (not accessible here).

其中最后一条（`vue-tsc` / `vite build` / 真实 Chromium / Windows 仓库集成）**已在本次合并中补齐并全部通过**（§4.2、§5）。
其余三条**仍然成立**：正式落库接口、持久化草稿、对虚拟床的动态沙盘评分，**均未实现**。

---

## 7. 遗留与待确认

1. **草稿槽位不避让真实床位**：`validatePose` 只对**草稿集合**判重，不与真实床位比对。
   实测 ward 9 有 4 张真实床（槽位 0–3），把草稿加在槽位 4/8 都正常；
   但**若加在被真实床占用的槽位上，两张床会视觉重叠**。
   影响面：仅视觉（模拟层，不写库）。建议后续在槽位下拉里把「已被真实床占用」的槽位置灰。**待业务方确认是否需要。**
2. **`bed_type` / 隔离床分级未参与编辑校验**：草稿可以落到与患者隔离属性不匹配的病房。属同一类「模拟层不做业务校验」的既定取舍。
3. **`floorKeyOf(-1)` 可解析**：合成床能被楼层归组，说明负 id 走得通链路；但**官方 API 必须拒绝负 id**（脚本已静态审计，运行时仍建议后端再加一道）。
4. **前几轮的 `v4_82 == v4_83` 现象未彻底归因**：已确认与「编辑面板增高导致固定裁剪失效」和「悬停浮层/剖切在帧间不一致」有关，投影法（§5.2）避开后结果自洽且可复现。归档材料已删除，不影响结论。
5. **既有遗留（与本包无关）**：`frontend/e2e/smoke.spec.ts` 仍未核对（CI 不含 Playwright）；`visibilitychange` 隐藏→可见分支无法在无头环境触发；减弱动效分支仅有静态护栏。

---

## 8. 合并后文件哈希（供下一次增量比对）

| 文件 | SHA256 | 字节 |
| --- | --- | --- |
| `frontend/src/modules/ward-map/scene-layout.ts` | `f7c1a4a3ee3b5fb75c01bbf5504daadf077e9dce697911548f2666ad8c3df3f1` | 8135 |
| `frontend/src/modules/ward-map/editor.ts` | `4eea48129f65f71d708ec344ab2ae7eae0d916a22aa74e31aa6f16aa487dd371` | 4312 |
| `frontend/src/components/WardScene3D.vue` | `3449a54f37bcbbc7b858f4bab8b475c3d35918c419d288d395520ac256e818d6` | 49694 |
| `frontend/src/components/WardBedEditor.vue` | `9ed4f03ad37bcb94c003882b280dc5e4e9e7b208ed15b177ade623b55b07d3de` | 6778 |
| `frontend/src/views/WardMapView.vue` | `43027837716c5606d6eace6530e8db25eec31df7b0711c8c8469fc0887b397b4` | 30859 |
| `frontend/src/modules/ward-map/ward-map.css` | `73a1af58cb5392f98391da6ca32db10019f820ef07b106893d7f90139ad3b0c1` | 23652 |
| `frontend/verify_ward_editor.cjs` | `5e800c33b9e01542045508cc02601e4d2b1cb48922beedb62d1c441909d5eec4` | 5959 |
| `docs/WARD_MAP_3D_EDITOR_V2.md` | `a75a9a406db54717cbd6369785e548d6ba47210732bd20799d1173458a783b5b` | 2402 |

---

## 9. 结语

- **可以合入**：六道源码闸门 + 类型检查 + 生产构建 + 72 项后端测试全绿；真实 Chromium 里草稿床被**逐像素证实**渲染出来，移除后**逐像素回到基线**；真实库业务表零写入。
- **不能夸大**：正式落库、草稿持久化、对虚拟床的沙盘评分**都没有做**，负 id 合成床**绝不可**译成官方床位 id。
- 本次为**本地提交，未 push**。
