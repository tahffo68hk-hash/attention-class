# Hospital Vision 3D V2 —— 本地集成与视觉验收报告

> 生成时间：2026-10-14
> 交付包：`Attention_Hospital_Vision_3D_V2_Delta_20261014.zip`
> 解压位置（项目外）：`E:\attention-handoff\hospital_vision_v2\`
> 结论：**WARD_MAP_V2_VISUAL_GATE = PASS**（18/18 真实浏览器检查通过，Console 0 error / 0 warning）

---

## 0. 一句话结论

V2 增量包已在本地前端**语义合并**完成（未整包覆盖），静态检查全绿，真实 Chromium WebGL
页面 18 项检查全部通过。过程中发现并修复 **2 个真实缺陷**（demo 床位坐标越界导致 28/44 床
飘在楼板外；three 0.186 下 `PCFSoftShadowMap` 已废弃产生 Console warning），并修正了
验收脚本自身的多处误判。**未进行任何 DeepSeek 付费调用**（`DEEPSEEK_EXTERNAL_ENABLED=false` 未动）。

---

## 1. 起点：V1 状态确认

任务要求「若已集成 V1 则按 V2 增量合并」。核查结果：

- Git HEAD = `fa3462b`（Clinical SaaS V1 集成 + 报告），**V1 未提交**，在工作树中。
- V1 已具备：只读后端接口 `GET /api/v1/ward-map`、页面路由 `/ward-map`、
  AppShell 一级导航「病区床位态势图」、`modules/ward-map/{types,demo,api}.ts`、`WardScene3D.vue`。
- V1 场景是**单层平面网格 + 简易方块床**，与 V2 的「整栋透明剖面」差距很大 → 走 V2 场景替换。

---

## 2. 为什么必须语义合并（不能整包覆盖）

| 维度 | 交付包基线 | 本地最新 | 结论 |
| --- | --- | --- | --- |
| 前端结构 | `src/lib/api.ts` 单文件、`App.vue` 一体外壳、路径式路由 | `api/ layouts/ stores/` 分层 + 命名路由 + 角色能力模型 | 不可覆盖 |
| 主题 | 自带 `.theme-dark` 补丁 + 硬编码色值 | Clinical SaaS 设计令牌（明/暗双主题） | 改为令牌化 |
| 组件 | 自带 `lib/labels` | `@/lib/labels`（与床位管理页共用词汇） | 保留本地 |
| 按钮 | 包内 `.btn` 可直接用 | 本地 `.btn` 次级 / `.btn--primary` 强调 | 保留本地语义 |

V2 包本身是**纯前端增量**（`WardScene3D.vue` / `WardMapView.vue` / `scene-layout.ts` /
`types.ts` / `demo.ts` / `ward-map.css` / `verify_v2_layout.cjs`），不含后端改动 ——
本轮因此**零后端代码变更**。

---

## 3. 合并内容

### 3.1 新增 / 重写

| 文件 | 处理 |
| --- | --- |
| `src/modules/ward-map/scene-layout.ts` | **新增**（V2 纯几何推导），并叠加本地防御性修正（见 §4.2） |
| `src/components/WardScene3D.vue` | **重写**为 V2 医院剖面渲染（外壳/玻璃/楼层/高精度病床/躺卧患者/三模式相机/拾取体积/资源释放），保留本地 `@/` 路径与明暗主题 |
| `src/views/WardMapView.vue` | **重写**并入三模式 + 楼层 chips + 床位定位 + Esc 关闭；保留本地 Modal 抽屉、`labelOf`、`@/api` 分层 |
| `src/modules/ward-map/ward-map.css` | **并入** V2 新增控件样式，全部改走本地设计令牌 |
| `verify_v2_layout.cjs` | **新增**（V2 布局门禁） |

### 3.2 保留未动

- 核心分配算法、评分权重（`recommendation.py` / `bed_policy.py`）—— **零改动**
- 数据库迁移（`alembic/`）、SQL —— **零改动**
- P3 手工床位状态规则、清洁释放二次确认
- P4 `/assistant` DeepSeek 一次确认 UI 与「未启用或未配置密钥」状态
- Clinical SaaS AppShell：分组侧栏、面包屑、Ctrl/Cmd+K、主题切换与持久化

---

## 4. 修复的真实缺陷

### 4.1 `PCFSoftShadowMap` 已废弃（Console warning）

three 0.186 起 `THREE.PCFSoftShadowMap` 被移除，运行时会 warning 并回退：

```
[warning] THREE.WebGLShadowMap: PCFSoftShadowMap has been removed. Using PCFShadowMap instead.
```

改为显式 `THREE.PCFShadowMap`（`WardScene3D.vue`），Console warning 归零。

### 4.2 demo 床位坐标越界（视觉严重缺陷）

**现象**：首轮截图里 2F/3F 的床位整整齐齐飘在建筑体外侧（右上角一堆"悬空病床"），
1F/2F 楼板上几乎看不到床。

**根因**：`demo.ts` 生成床位 `simulated_position` 时，**z 少加了所属房间的 z 基准**：

```ts
// 错误：床位 z 是房内局部坐标
simulated_position: { x: x + 1.15 + (j % 4) * 2.35, z: 1.65 + Math.floor(j / 4) * 3.25 }
// 正确：与后端 ward_map.simulated_positions 的 base_z + 偏移 口径一致
simulated_position: { x: x + 1.15 + (j % 4) * 2.35, z: z + 1.65 + Math.floor(j / 4) * 3.25 }
```

而 `scene-layout.ts` 按楼层 `minZ` 归一化，于是 2F/3F 床位 z 变成 **-13.15 / -30.15**。

**数值验证**（复刻布局层归一化逻辑）：

| 楼层 | 修复前越界床位 | 修复后 |
| --- | --- | --- |
| 1F | 0 / 16 | 0 / 16 |
| 2F | **14 / 14** | 0 / 14 |
| 3F | **14 / 14** | 0 / 14 |

**双层修复**（不只改数据，也加固布局层）：

1. `demo.ts`：床位 z 继承房间基准。
2. `scene-layout.ts`：床位按「房间基准 + 房内偏移」换算；且楼板 `width/depth`
   同时覆盖房间与**床位**范围（`BED_MARGIN = 1.6`），任何一侧数据异常都不会把床位甩出楼板。

修复后用**后端真实 3 列口径**数据复算，3 层 48 床同样 `OUTSIDE=0`，确认对真实数据也成立。

### 4.3 验收脚本自身的三处误判（非应用缺陷，如实记录）

排查 hover 时连续踩坑，均为**脚本/工具**问题，不是产品缺陷，但都曾导致误判：

1. **`<<exited>>` 被当成失败** —— 该标记表示 CLI 进程正常退出（= 成功）。
   第一轮 15 项「失败」全部由此产生。
2. **同步循环读不到 Vue 异步渲染的 tooltip** —— hover 扫描 500 点全部落空，
   改成「派发 pointermove → `requestAnimationFrame` 让出事件循环 → 再读 DOM」后立即命中。
3. **`js()` 只解一层 JSON** —— CDP 会把对象再包一层字符串，导致 `hit` 是字符串而非 dict，
   `if isinstance(hit, dict)` 分支永不进入（截图与点击日志静默跳过）。

此外记录一条**本机工具行为**：agent-browser 的 CDP 目标在连续 `mouse` /
`mouse wheel` 操作后会被重置到 `about:blank`（已实测：期间 `cursor` 确实变为 `pointer`，
说明拾取命中，随后 tab 漂走）。因此 hover / 点击证据改由页面内 `dispatchEvent` 派发 ——
它与真实鼠标进入**同一个** `pointermove`/`click` 监听、同一个 `pick()` 射线拾取、
同一套 `emit('hover'/'select')`，差异只在"谁来派发事件"。

---

## 5. 测试结果

### 5.1 静态检查

| 项 | 结果 |
| --- | --- |
| `node verify_v2_layout.cjs` | `V2_LAYOUT_GATE: PASS`（44 demo beds, 3 floors, stable positions, no missing mappings） |
| `vue-tsc --noEmit` | **0 error** |
| `vite build` | 通过（4.42s；仅 `WardMapView` chunk 575 kB 的常规体积提示） |
| `pytest tests_ward_map` | **7 passed** |
| `pytest`（8 个套件全量，含真实 MySQL） | **189 passed**（129s，唯一 warning 是 starlette 的 httpx 弃用提示，与本轮无关） |

### 5.2 真实浏览器验收（Chromium + WebGL，1440×900 / 390×844）

数据源：**明确标识的合成演示数据**（`SYNTHETIC_DEMO`，3 层 / 6 病房 / 44 床，
状态分布 空闲 21 / 预占 7 / 已住 8 / 清洁 5 / 维护 3）。

**18 / 18 PASS，FAILURES: 0**

| # | 检查项 | 结果 |
| --- | --- | --- |
| 1 | 会话注入后到达 `/ward-map` | PASS |
| 2 | 明确标识为合成演示数据 | PASS |
| 3 | 演示数据为 44 床 | PASS |
| 4 | 楼层 chips ≥ 3 层 | PASS（1F 16床 / 2F 14床 / 3F 14床） |
| 5 | WebGL 画布存在且尺寸非零 | PASS（926×520，ctx=true） |
| 6 | Hover 命中床位并显示信息卡 | PASS（`101-01 ● 空闲`，cursor=pointer） |
| 7 | 点击床位打开详情抽屉 | PASS（床位信息 + 脱敏声明 + 流水区） |
| 8 | 状态筛选生效且 3D 仍在 | PASS（OCCUPIED → 8/44） |
| 9 | 二维列表降级可用（≥40 项） | PASS（44 项） |
| 10 | 暗色主题切换生效 | PASS（`theme-dark`） |
| 11 | 桌面无横向溢出 | PASS（scrollWidth == clientWidth） |
| 12 | 移动 390 无横向溢出 | PASS |
| 13 | 移动端 3D 或列表可用 | PASS（canvas 存活） |
| 14–17 | 回归 `/dashboard` `/beds` `/assistant` `/audit` | PASS（4/4，标题正确、无错误块） |
| 18 | 全流程 Console 0 error | PASS（**warning 0 条**） |

### 5.3 视觉验收（逐项实际看图，非仅编译通过）

| 验收要求 | 实际观察 | 判定 |
| --- | --- | --- |
| 整栋透明医院剖面 | 三层楼板 + 玻璃幕墙 + 角柱 + 环梁 + 顶部檐口，正面完全剖开；44 床按状态色（绿/蓝/橙/紫/灰）分布可辨 | PASS |
| 多楼层分层展开 | `☰ 分层展开` 三层竖向拉开，每层 14–16 床全部可见、无遮挡 | PASS |
| 医疗床与躺卧患者特写 | 病床含床垫/床头/护栏/枕头；入住床位有躺卧患者（被褥+枕头+头部），无穿模、无「人浮在床上」 | PASS |
| Hover 信息与点击详情抽屉 | 信息卡显示床号+状态色点+科室病房+脱敏说明；抽屉含床位信息、隔离标记、空间坐标声明、跳转按钮 | PASS |
| **建筑比例** | 层高 4.9、开间 10.3、走廊与墙体厚度成比例，非「一堆方块」 | PASS |
| **透明墙遮挡** | 玻璃 `opacity 0.09~0.1` + `depthWrite:false`，正面不封闭；床位无遮挡带 | PASS |
| **床位间距** | 横向 2.35 / 纵向 3.25，床间留出通行间隙，无重叠 | PASS |
| **患者穿模** | 患者几何贴合床垫与枕头 | PASS |
| **镜头构图** | 正交 2.5D，包围盒自适应缩放，窄屏自动后退；单层聚焦/分层展开各自取景 | PASS |
| **灯光** | 半球光 + 主光（2048 阴影贴图）+ 补光；暗色主题下调曝光，白色病房不刺眼 | PASS |

### 5.4 回归

- 后端：`tests tests_p1p2 tests_p25 tests_p3 tests_p4 tests_p15 tests_m1_local tests_ward_map`
  全量 **189 passed**（含 P3 门禁回归、P4 DeepSeek provider 与 pilot 并发闸门）。
- 前端既有页面：`/dashboard` `/beds` `/assistant` `/audit` 四条路由实测无回退。
- Clinical SaaS 外壳：明暗主题、快捷搜索、侧栏导航均正常。
- DeepSeek：`DEEPSEEK_EXTERNAL_ENABLED=false` 未动，**本轮零外发付费调用**。

---

## 6. 修改文件清单

```
新增  frontend/src/modules/ward-map/scene-layout.ts
新增  frontend/verify_v2_layout.cjs
重写  frontend/src/components/WardScene3D.vue
重写  frontend/src/views/WardMapView.vue
改写  frontend/src/modules/ward-map/demo.ts          （修床位 z 越界）
改写  frontend/src/modules/ward-map/ward-map.css     （并入 V2 控件样式，令牌化）
改写  frontend/src/modules/ward-map/types.ts         （加 SceneMode）
新增  frontend/src/modules/ward-map/api.ts           （V1 遗留，适配本地 api/ 分层）
证据  docs/screenshots/v2_01..17*.png               （17 张真实浏览器截图）
证据  docs/WARD_MAP_V2_INTEGRATION.md               （本文件）
```

**未触碰**：`backend/app/**`、`backend/alembic/**`、`sql/**`、`docker-compose.yml`、
`recommendation.py`、`bed_policy.py`、任何 P3/P4 业务状态与路由逻辑。

---

## 7. 已知限制（如实声明）

1. **hover / 点击取证用页面内 `dispatchEvent`** 而非 OS 级鼠标，原因见 §4.3 第 4 点
   （本机 CDP 目标漂移）。事件通路与真实鼠标完全一致，但严格意义上不是物理鼠标驱动。
2. **Playwright e2e 未跑**：本机 `node_modules` 缺 `@playwright/test`；CI 也只跑
   `npm run build`，故非阻塞。
3. **`WardMapView` chunk 575 kB**：three.js 全量引入所致（gzip 148 kB），
   路由已懒加载，不影响首屏；如需进一步优化可对 three 做 manualChunks 拆分。
4. 移动端沿用同一套 Three.js 场景（未做手势简化），390px 下可用且无溢出，
   但未针对触屏做双指旋转等原生手势。

---

## 8. 门禁声明

- `verify_v2_layout.cjs` → **PASS**
- `vue-tsc --noEmit` → **0 error**
- `vite build` → **通过**
- 真实 Chromium WebGL 视觉与交互验收 → **18/18 PASS，Console 0 error / 0 warning**
- 视觉六项（建筑比例 / 透明墙遮挡 / 床位间距 / 患者穿模 / 镜头构图 / 灯光）→ **逐项看图确认通过**

> **WARD_MAP_V2_VISUAL_GATE = PASS**