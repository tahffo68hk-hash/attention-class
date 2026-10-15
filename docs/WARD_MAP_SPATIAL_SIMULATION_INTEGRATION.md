# 病区床位态势图 —— 参数化空间布局 + 只读调度沙盘 V1 集成报告

状态：**`WARD_MAP_SPATIAL_SIMULATION_V1 = PASS`**（带 2 项静态覆盖说明，见 §7）
集成方式：**语义增量合并** ｜ 集成本地基线：`243562c`
交付包：`Attention_Ward_Map_Spatial_Simulation_V1_Delta_20261015.zip`
交付包自述基线：候选 `68305c6` / 归档候选 `ccb636b`（**不是**本仓库当时的 HEAD）
提交：见 §9 ｜ **NO PUSH**

---

## 0. 一句话结论

参数化建筑空间布局（中央走廊 + 双侧镜像病房 + 门洞 + 床位朝向）与只读调度沙盘
（`POST /api/v1/ward-map/simulate`）已在本地真实环境完成集成与验收：后端真实 MySQL 只读回归
零写入、前端类型/构建/四套源码守卫全通过、**Chromium 真实 WebGL** 下三种沙盘轮廓
（候选青 / 命中金 / 停用灰）均已取得像素级证据。
集成过程中发现并修复了交付版本的一个真实缺陷（见 §6.1）。

---

## 1. 为什么必须做语义合并（不能直接覆盖）

交付包 `HANDOFF.md` 明确要求「逐文件比对 SHA256，若当前文件不匹配则按语义增量合并，
**不得整体覆盖** `WardScene3D.vue`，并保留 `9953835` 之后的动画修复」。

实际比对结果：`BASELINE_SHA256.json` 共 14 条（8 条 `new` + 6 条 `modify`），
其中——

- 8 个 `new` 文件本地**全部缺失** → 按 `PATCHED_FILES/` 原样落地，逐个校验
  `sha256 == patched_sha256`；
- 6 个 `modify` 文件在**基线侧与交付侧都不同**（本地自 `9953835` 起已含
  Hover V3 浮起、Click 拾取体、楼层过渡、V2 布局等改动）→ 一律**只按语义增量**合入，
  不 `git apply`、不整文件覆盖。

因此本轮的 6 个 `modify` 文件是**手写合并**，逐段确认过保留项。

---

## 2. 实际落地内容

### 2.1 新增文件（8 个，原样落地并校验 SHA256）

| 文件 | 作用 |
| --- | --- |
| `backend/app/api/v1/ward_sandbox.py` | `POST /ward-map/simulate`，仅 ADMIN/NURSE |
| `backend/app/schemas/ward_sandbox.py` | 输入 `extra="forbid"`，拒绝患者字段；输出含三个只读标志位 |
| `backend/app/services/ward_sandbox.py` | 只读快照 + What-if 假设，复用正式硬约束/评分/求解器 |
| `backend/tests_ward_map/test_sandbox.py` | 8 项沙盘测试 |
| `frontend/src/modules/ward-map/sandbox.ts` | 前后端沙盘契约类型 |
| `frontend/src/components/WardSimulationPanel.vue` | 沙盘面板（本地适配 HTTP 层与 `.btn` 语义） |
| `frontend/verify_spatial_simulation.cjs` | 空间布局 + 沙盘契约守卫 |
| `docs/WARD_MAP_SPATIAL_REDESIGN_AND_SIMULATION.md` | 交付方说明（原样保留） |

### 2.2 语义增量合并的文件（6 个）

- **`backend/app/api/v1/router.py`** —— 手工加入 `import ward_sandbox` 与
  `api_router.include_router(ward_sandbox.router)`，未覆盖同文件里本轮之前的其它路由改动。
- **`frontend/src/modules/ward-map/scene-layout.ts`** —— 重写为参数化布局：
  `FLOOR_HEIGHT=4.9`、`ROOM_WIDTH=12.2`、`CORRIDOR_WIDTH=4.5`，
  每栋楼共享 `bays/roomDepth/corridorZ`，房间沿中央走廊南北交替镜像，
  `orientation = side === 'north' ? 0 : Math.PI`。
  刻意**忽略**后端 `simulated_position` 旧散点坐标。
- **`frontend/src/components/WardScene3D.vue`** —— 增量合入 4 个新 props
  （`simulationUnavailableIds/CandidateIds/AssignedIds/TopBedId`）、
  `buildBed(..., orientation)` 与床位旋转、按 `r.side` 重建房间隔断与 2.4 单位门洞、
  走廊板改用 `f.corridorZ/corridorWidth`，以及高亮链路与新增 watcher。
  **保留**：Hover V3 浮起与固定拾取体、五态主色、透明遮挡与恢复、
  楼层过渡（含 `visibilitychange` 成对注册）、阴影仅在几何/楼层变化时重算、
  减弱动效路径。
- **`frontend/src/views/WardMapView.vue`** —— 加入沙盘状态块与 4 个 `:simulation-*` 传参、
  工具栏「调度模拟」入口、二维列表「模拟已匹配」徽标、抽屉内沙盘段；
  并在 `load()` 与 `setDemo()` 开头调用 `exitSandbox()`，保证真实快照一变旧结论立即失效。
- **`frontend/src/modules/ward-map/ward-map.css`** —— 追加约 200 行沙盘样式。
  **关键点**：抽屉走 `Modal` 的 `Teleport` 渲染到 `<body>`，因此抽屉内样式只能使用
  **全局设计令牌**，不能用页面局部的 `--wm-*` 别名（否则抽屉里颜色全丢）。
- **`frontend/e2e/ward-spatial-sandbox.spec.ts`** —— 本地适配登录选择器与截图目录。

### 2.3 本轮本地新增

- **`frontend/verify_reduced_motion_parity.cjs`** —— 见 §6.1，修复对应的回归守卫。

---

## 3. 后端验证（真实 MySQL，隔离实例 3307）

| 项目 | 结果 |
| --- | --- |
| `python -m compileall` | 通过 |
| OpenAPI 路径数 | **38 → 39**，含 `POST /api/v1/ward-map/simulate` |
| `pytest -q` 主套件 | **57 passed** |
| `pytest backend/tests_ward_map` | **15 passed**（8 沙盘 + 7 态势图） |
| 真实库只读回归 `sandbox_api_check.py` | **PASS** |

真实库回归的具体观测：

- 200 响应携带 `scenario_kind=SYNTHETIC_ONLY`、`preview_only=true`、`no_database_writes=true`；
- `optimized.method=exact_min_cost_flow`、`proven_optimal=true`（最优性来自真实求解器返回值）；
- 首位候选 `C-ICU-03 73.36`，五维分项键齐全；
- 请求体夹带患者字段 → **422 `VALIDATION_ERROR`**（`extra="forbid"` 生效）；
- `VIEWER` 调用 → **403 `PERMISSION_DENIED`**；
- What-if 停用一张床：`applied_unavailable_bed_ids` 正确回显、候选数 4 → 3、
  `snapshot_fingerprint` 不变（说明假设只在临时视图上生效，未污染快照）；
- **写入计数不变**：`Bed` 44 / `BedAllocation` 23 / `AdmissionRequest` 22；
  `AuditLog` 262 → 265 仅来自那次**故意的 403 越权尝试**（越权用独立会话立即提交，保证失败也留痕）。

---

## 4. 前端静态验证

| 守卫 | 结果 |
| --- | --- |
| `verify_spatial_simulation.cjs` | `SPATIAL_LAYOUT: PASS`（3 层、44 床唯一落位、0 重叠、走廊与墙体净空、刷新确定性）+ `SANDBOX_CONTRACT_TS: PASS` |
| `verify_v2_layout.cjs` | `V2_LAYOUT_GATE: PASS` |
| `verify_hover_visual.cjs` | **10/10 PASS** |
| `verify_webgl_transition_guards.cjs` | **17/17 PASS** |
| `verify_reduced_motion_parity.cjs`（本轮新增） | **12/12 PASS**；变异源文件反向验证 **7/12 FAIL，退出码 1** |
| `vue-tsc --noEmit` | **exit 0** |
| `vite build` | **成功，4.09 s**；`WardMapView-*.js` 592.19 kB（gzip 154.31 kB） |

---

## 5. Chromium 真实 WebGL 验收

驱动方式：受管 Node 直接执行 `agent-browser`，每阶段在**单次 batch** 内完成
「登录 → 进页面 → 操作 → 截图 → console/errors」，避免页面状态跨调用丢失。
控制台在所有阶段**只有 `[vite] connecting/connected` 调试输出，零 JS 错误**。

### 5.1 空间布局与沙盘交互

| 证据 | 内容 |
| --- | --- |
| `v4_01_building_parametric.png` | 参数化整栋剖面（中央走廊 + 双侧镜像病房 + 门洞） |
| `v4_02_single_floor_axis.png` / `v4_03_exploded.png` | 单层聚焦 / 分层展开（轴线一致） |
| `v4_04..v4_07` | 沙盘开面板 / 算出方案 / 定位联动 / 二维列表徽标 |

沙盘运行时的**现场文本证据**（DOM 直读）：

```json
{"metrics":"模拟安排人数 2 / 2 | 优先级和 4 | 评分合计 158.16 | 求解时间 0.057 ms",
 "note":"exact_min_cost_flow · 已证明该模拟目标最优 · 零写入","pairs":2}
{"drawerHasSandbox":true,
 "drawerNotice":"此床位出现在当前模拟方案中。不会修改真实床位或分配。"}
{"listMode":true,"rows":44,"badges":["C-102-04"]}
```

### 5.2 三种沙盘轮廓的像素级判定（核心证据）

方法：把舞台滚到视口中央 → 读 `canvas.getBoundingClientRect()` → **剔除固定页头与底部徽标**
后取 3D 场景区 → **±3px 对齐搜索**（消除不同滚动位置带来的整数取整错位）→
通道关系色相探测 + 逐像素比对。

同机位三张图：`v4_18`（基线，已清空全部假设）/ `v4_17`（1 条虚构申请）/
`v4_19`（追加 What-if 停用 `C-101-02`）。
该申请的候选集现场直读为 4 张床，What-if 后降为 3 张：

```
候选(4): C-102-04 79.24(命中) / C-101-02 78.92 / C-102-02 77.84 / C-ICU-03 42.30
候选(3): C-102-04 79.24(命中) /             C-102-02 77.84 / C-ICU-03 42.30
```

| 轮廓 | 判据 | 结果 |
| --- | --- | --- |
| **候选青** `#0C9D9A` | 场景区青色像素 基线 2090 → 申请 **2355（+265）** | ✅ 可辨 |
| **命中金** `#E5B348` | 场景区金色像素 基线 0 → 申请 **175（+175）** | ✅ 可辨 |
| **停用灰** `#64748B` | 同一批 **216 px** 上，青色系整体消失、蓝灰系等量新增 | ✅ 可辨 |

停用床的「青→灰」换色被量化成一对一替换（同一窗口 15400 px，变化 216 px = 1.40%）：

```
消失： #73BDBC ×92  #A7CDCD ×39  #8DC5C5 ×33  #C1D6D6 ×31  #3FADAB ×3 …
新增： #8F9AA9 ×91  #B5BCC4 ×39  #A2ABB6 ×32  #C8CDD1 ×31  #748296 ×3 …
```

场景区整体差异：**基线→申请 652 px（0.174%）**，**申请→What-if 468 px（0.125%）**。

可肉眼复核的证据图：

- `v4_20_scene_base_vs_request.png` —— 上=基线（全无轮廓）／下=申请后（1 金框 + 3 青框）
- `v4_21_scene_request_vs_whatif.png` —— 上=申请后／下=What-if 后（该床轮廓换色）
- `v4_22_unavailable_bed_teal_to_gray_6x.png` —— 停用床 6 倍最近邻放大：左青右灰

### 5.3 压力与契约

| 项目 | 结果 |
| --- | --- |
| 观察模式快速切换 | `{"fired":100,"toggled":6}`（100 次模式切换 + 6 次沙盘开关） |
| `visibilitychange` | 已派发（`{"hidden":false}`） |
| 压力后 / 回前台截图 | `v4_08_after_stress.png` / `v4_09_after_visibility.png`（**两份字节相同，属预期**，见 §7） |
| 控制台 | 仅 vite debug，**零 JS 错误** |
| WebGL 上下文 | `{"canvas":true,"webgl":true,"w":926,"h":520}` |
| 只读契约文案 | `noWrites / previewOnly / fictional` 三项 **全 true** |

---

## 6. 本轮发现的缺陷与处置

### 6.1 交付版本真实缺陷（已修复）

**`WardScene3D.vue` 的 `animateEffectsReduced()` 透明度链漏了 `unavailable`（及 `top`）。**

`WardScene3D.vue` 有两条高亮落地路径：正常动效 `animateEffects()` 与用户开启
「减弱动效」时的 `animateEffectsReduced()`。交付版本中：

- **颜色链**两条都正确（`unavailable → #64748B`）；
- **透明度链**只有动效路径正确（`… unavailable ? 0.64 …`），
  减弱动效路径写成 `on ? 0.92 : selected ? 0.75 : assigned ? 0.82 : candidate ? 0.5 : 0`。

后果：在减弱动效模式下，一张**仅被 What-if 临时停用、又不在候选集**的床位会拿到
灰色色值却 `alpha = 0`，`outline.visible` 为假 —— 3D 上灰色轮廓**整块消失**，
与交付说明「减弱动效路径保留状态与遮挡语义」的要求不符。

**处置**：把透明度链补齐为与动效路径逐项一致
（`hover > selected > unavailable > assigned > top > candidate > 0`，
取值 0.92/0.75/0.64/0.82/0.75/0.5/0），代码中以
`[LOCAL HARDENING 2026-10-15]` 注释标明本地加固点与原因。

**回归守卫**：新增 `frontend/verify_reduced_motion_parity.cjs`，
断言两条分支的颜色优先级、透明度优先级顺序与常量集合完全一致。
**反向验证**：把修复的 `unavailable` 分支删掉后守卫 **7/12 FAIL、退出码 1**，
证明守卫确实会失败而不是恒过。

### 6.2 采集驱动缺陷（不是产品缺陷，已修）

第一版 What-if 采集脚本在**同一个同步任务**里既改 `<select>` 值、又立刻
`button.click()`。Vue 的 `v-model` 已更新 `hiddenBed`，但模板上
`:disabled="!hiddenBed"` 要等下一次渲染才解除，此刻 DOM 里按钮仍是 disabled，
**`click()` 被浏览器丢弃**，假设从未加入 —— 表现为「What-if 前后截图字节完全相同」。

这也解释了为什么「添加虚构申请」一直正常：它走的是 agent-browser 的独立
`find text … click` 步骤，中间已经过了一次渲染。
**修法**：What-if 同样拆成两步（先选床、隔一次渲染、再点按钮）。
已在脚本注释中固化该陷阱。

### 6.3 证据方法学缺陷（已修）

- **画布矩形取整导致整体错位**：`getBoundingClientRect()` 返回小数，
  不同滚动位置取整后差 1px，就足以让整个 3D 画面错开，差异铺满画布、
  包围盒等于全画布（指纹是「两步差异量几乎相同」）。
  修法：**±3px 对齐搜索**后再衡量差异。
- **裁剪把固定页头算进了「画布」**：画布 `top≈22`，但应用页头是 `position:fixed`
  覆盖在画布上方，页头的主题蓝 `#6096FA` 被误判成「青色轮廓」、页头金色图标
  被误判成「金色轮廓」。修法：场景区上下各内缩若干像素剔除页头与底部徽标。
- **灰色判据方向写反**：`#64748B = (100,116,139)` 是**冷板岩灰（r < g < b）**，
  而初版判据要求 `r >= g-2`，正好把它排除，于是得出「灰色从未绘制」的**错误结论**。
  修法：改用蓝灰判据并以逐像素色差表交叉验证（即 §5.2 的 216 px 替换表）。

> 记录这三条是因为它们都会**反向误导结论**（把「有」判成「无」），
> 而非只是精度问题。

### 6.4 已核实不构成问题的一点

`sceneBedPalette.AVAILABLE.outline = '#F3C94A'`（金）与沙盘命中金 `#E5B348` 同色系，
理论上「沙盘首选 `top`」若不走候选分支会呈现空闲床自身的金色轮廓、与命中金混淆。
**已核实不可达**：`sandboxTopBedId` 本身即从 `candidates` 中筛选而来，
`top` 必然同时是 `candidate`，而颜色链先判 `assigned`、再判 `candidate`，
因此在现行实现下 `top` 永远走青或金，不会落到 palette 分支。故不修改、仅记录。

---

## 7. 未覆盖项与限制（如实声明）

1. **减弱动效路径只做了静态验证**。本机 headless Chromium 实测
   `prefers-reduced-motion: reduce = false`（`no-preference = true`），
   因此 `animateEffectsReduced()` 分支**在真实浏览器里没有被执行过**；
   §6.1 的修复由静态守卫 + 变异反向验证覆盖，未做真实浏览器复核。
2. **`visibilitychange` 的「隐藏→回前台补齐」未真正跑通**：headless 下
   `document.hidden` 恒为 `false`，派发事件不产生可见变化 —— 这正是
   `v4_08` 与 `v4_09` 字节相同的原因（属预期，不是失败）。
   该路径由 `verify_webgl_transition_guards.cjs` 的静态护栏覆盖（17/17 PASS）。
3. **`frontend/e2e/ward-spatial-sandbox.spec.ts`（Playwright）仍未执行**：
   本环境无法下载 Playwright 浏览器。已用 agent-browser 驱动真实 Chromium 完成
   等价验收（§5），但该 spec 文件本身**未经运行**。
4. **建筑几何是演示空间**，不是 BIM，也不是医院真实平面图的测量数据；
   三维 Y 抬升纯属视觉表达。评分仍使用 `beds.position_x/position_y`，两者无关。
5. **沙盘是依据当前快照的计算结果，不是分配承诺**；真实业务数据变化后必须重算。
   所有正式分配、入住、换床仍走原业务 API。

---

## 8. 验收判定

```
SPATIAL_CODE_TESTS              = PASS
SANDBOX_LOGIC_TESTS             = PASS
SANDBOX_READONLY_REGRESSION     = PASS   (真实 MySQL，零业务写入)
FRONTEND_STATIC_GUARDS          = PASS   (12/12 + 10/10 + 17/17 + 2 项)
FRONTEND_TYPECHECK_AND_BUILD    = PASS   (vue-tsc exit 0 / vite build 4.09s)
WINDOWS_WEBGL_GATE              = PASS   (Chromium 真实 WebGL，零控制台错误)
SANDBOX_OUTLINE_PIXEL_PROOF     = PASS   (候选青 +265 / 命中金 +175 / 停用灰 216px 换色)
WARD_MAP_SPATIAL_SIMULATION_V1  = PASS   (减弱动效与 visibility 恢复为静态覆盖)
```

---

## 9. 变更清单与提交

### 新增（9）

```
backend/app/api/v1/ward_sandbox.py
backend/app/schemas/ward_sandbox.py
backend/app/services/ward_sandbox.py
backend/tests_ward_map/test_sandbox.py
docs/WARD_MAP_SPATIAL_REDESIGN_AND_SIMULATION.md     （交付方说明，原样）
docs/WARD_MAP_SPATIAL_SIMULATION_INTEGRATION.md      （本报告）
frontend/src/components/WardSimulationPanel.vue
frontend/src/modules/ward-map/sandbox.ts
frontend/verify_spatial_simulation.cjs               （交付守卫，原样）
frontend/verify_reduced_motion_parity.cjs            （本轮新增守卫，见 §6.1）
frontend/e2e/ward-spatial-sandbox.spec.ts            （本地适配；未运行，见 §7.3）
```

### 修改（5）

```
backend/app/api/v1/router.py
frontend/src/components/WardScene3D.vue              （含 §6.1 本地加固）
frontend/src/modules/ward-map/scene-layout.ts
frontend/src/modules/ward-map/ward-map.css
frontend/src/views/WardMapView.vue
```

### 证据（`docs/screenshots/`，20 张）

```
v4_01..v4_03  参数化布局（整栋剖面 / 单层聚焦 / 分层展开）
v4_04..v4_07  沙盘面板 / 方案 / 定位联动 / 列表徽标
v4_08..v4_09  压力测试后 / visibilitychange 后（字节相同，见 §7.2）
v4_10..v4_11  沙盘高亮（单层聚焦 / 分层展开）
v4_13         二维列表「模拟已匹配」徽标
v4_14..v4_16  同视口 A/B/C 对照（沙盘开 / 有申请 / 加 What-if）
v4_17..v4_19  同机位放大型对照（基线 / 有申请 / 加 What-if）
v4_20..v4_22  像素级证据（基线vs申请 / 申请vs What-if / 停用床青转灰 6x）
```

> 已删除 `v4_12_whatif_unavailable.png`：它由 §6.2 的有缺陷驱动采集，
> 内容与 `v4_11_highlight_exploded.png` **字节完全相同**，文件名却在声称
> 「停用床」，留着会误导复核者；该场景已由 `v4_17/18/19` 正确覆盖。

| | |
| --- | --- |
| 集成提交 | 见 git log 顶部 `feat(ward-map): 集成参数化空间布局与只读调度沙盘 V1` |
| 集成前基线 | `243562c` |
| 推送 | **NO PUSH**（按约定本轮不推送） |
