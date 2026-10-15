# UI/UX WebGL Transition Followup 增量集成报告

日期：2026-10-15
交付包：`Attention_UIUX_WebGL_Transition_Followup_20261015.zip`
（解压于项目外 `E:\attention-handoff\UIUX_WebGL_Transition_Followup_20261015\`）
集成基线：本仓库 `281569e`（Hover Visual V3 / Product Polish 检查点）

---

## 1. 交付包构成与哈希核对

| 文件 | 说明 |
| --- | --- |
| `FILES/src/components/WardScene3D.vue` | 唯一的源码改动（候选实现） |
| `FILES/verify_webgl_transition_guards.cjs` | 源码级守卫（9 条断言） |
| `FILES/docs/UIUX_DEEP_POLISH_FINAL_GATE.md` | 交付方门禁记录，结论 `BLOCKED` |
| `UIUX_FOLLOWUP.patch` | 上述三处的统一补丁 |
| `BASELINE_SHA256.json` / `PACKAGE_HASHES.json` | 基线哈希与包内哈希清单 |

包内自洽性核对通过（`PACKAGE_HASHES.json` 中每个文件的 sha256 与解压产物一致）。

## 2. 基线漂移判定（关键结论：**漂移，不可覆盖**）

| 对象 | sha256（前 8 位） | 字节 |
| --- | --- | --- |
| 交付包 baseline（候选 `7017658`） | `1ada5668` | — |
| 交付包 patched（候选 `a94514b`） | `b24caed5` | 30810 |
| **本机** `frontend/src/components/WardScene3D.vue` | **`8b5a66c3`** | **41509** |

本机文件与 baseline、patched **都不相同**。原因是本仓库的 V2/V3 版本做过本地适配
（类型与布局引用改走 `@/modules/ward-map/*`、透明画布、暗色曝光、软阴影、
患者几何加固，以及 V3 的 Hover 视觉与 `hover-visual.ts` 模块化），
并非交付方那份压缩风格的候选实现。

因此**未使用 `git apply`、未整文件覆盖**，改为逐条比对语义后做增量合并；
交付方 `HANDOFF.md` 也明确要求「Apply only if current Windows code does not already
include equivalent changes；Do not override any more recent fixes」。

## 3. 逐处语义合并清单

合并前先做语义存在性检查，7 个特征点**全部缺失**，故均需合入：

| # | 交付意图 | 本机合并落点 | 备注 |
| --- | --- | --- | --- |
| 1 | 记录被打断的过渡 | `resumeTransitionAfterVisibility` 声明 | 新增内部状态 |
| 2 | 射线检测前同步世界矩阵 | `updateOcclusionTargets()` 内 `root.updateWorldMatrix(true,true)` + `camera.updateMatrixWorld()` | 纯增强 |
| 3 | 遮挡目标可回退到选中床 | `const targetId = hoveredId ?? props.selectedId` | 见下 §3.1 |
| 4 | 隐藏标签页不排效果帧 | `startEffects()` 首部 `if (document.hidden) { stopEffects(); return }` | 防后台节流积压 |
| 5 | 楼层过渡中选中床也重算遮挡 | `applyMode()` 帧循环 `hoveredId !== null \|\| props.selectedId !== null` | 依赖 #3 |
| 6 | 隐藏时取消相机/楼层帧，恢复时补齐 | 新增 `onDocumentVisibility()` + `visibilitychange` 注册/反注册 | 见下 §3.2 |
| 7 | 卸载时清掉 pending 过渡记号 | `destroy()` 末尾 `resumeTransitionAfterVisibility = false` | — |

### 3.1 为什么必须同时引入 `targetId` 回退（交付包 baseline 特性）

交付包第 5 条改动（`applyMode` 里让 selectedId 触发 `updateOcclusionTargets()`）
只有在「遮挡目标选择本身认识 selectedId」时才有意义。本仓库 V3 的
`updateOcclusionTargets()` 原本只读 `hoveredId`，若只照搬第 5 条，
选中一张床后切楼层会**空转**（`hoveredId` 为 null → 命中集为空 →
既不会有正确的淡化，也不会清掉上一帧的过期淡化）。

因此按交付意图补上回退链：**悬停优先，其次当前选中床**。
这属于行为扩展（选中态现在也参与遮挡淡化），已在真实浏览器中单独验证（见 §4）。

### 3.2 本机原本**没有** `visibilitychange` 监听

V3 版本只在 `startEffects()` 里判断过 reduced-motion，从未监听页面可见性。
所以第 6 条不是「改造既有函数」，而是**新增**：函数体、`initialize()` 内的
`document.addEventListener('visibilitychange', ...)`、以及 `destroy()` 内的成对
`removeEventListener`。守卫脚本对此单独加了断言，防止只加注册漏加反注册。

### 3.3 未采纳的内容

- 交付方 `FILES/verify_webgl_transition_guards.cjs` **未直接使用**：
  它把 typescript 路径写死为 `/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript`，
  且断言的是压缩写法（如 `hoveredId!==null||props.selectedId!==null`），
  在本仓库的格式化风格下必然误报。已按本仓库风格重写为
  `frontend/verify_webgl_transition_guards.cjs`，断言强度不降并额外补了 2 条（见 §5）。
- 交付方 `UIUX_DEEP_POLISH_FINAL_GATE.md` 中「Windows 不可访问 / 无法构建 / 无 WebGL 证据」
  的结论**不适用于本机**，原文已收录于 `docs/UIUX_DEEP_POLISH_FINAL_GATE.md` 供追溯，
  本机实际门禁结论见 §4。

## 4. 验证记录

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 源码级过渡守卫 | **17/17 PASS** | `frontend/verify_webgl_transition_guards.cjs` |
| V3 悬停视觉回归 | **10/10 PASS** | `frontend/verify_hover_visual.cjs` |
| V2 布局回归 | **PASS**（44 床 / 3 层 / 映射稳定） | `frontend/verify_v2_layout.cjs` |
| TypeScript 类型检查 | **0 错误** | `vue-tsc --noEmit` |
| 生产构建 | **成功**（4.63s） | `vite build`，产出 `WardMapView-*.js` 580 kB |
| 后端 OpenAPI 路径数 | **38**（与集成前一致，本次未动后端） | `GET /openapi.json` |
| 后端测试套件 | **57 passed**（44.40s，真实 MySQL） | `pytest -q`，`testpaths=tests` |
| 真实浏览器：登录 → 3D 页面 | 通 | `v3f_01_building.png`（44 床 / 4 楼层） |
| 真实浏览器：选中床 + 单层聚焦 | 通 | `v3f_02_selected_focus.png` |
| 真实浏览器：分层展开过渡中/落定 | 通，无过期淡化残留 | `v3f_03_tweening.png`、`v3f_04_settled.png` |
| 真实浏览器：切回整栋剖面 | 通 | `v3f_05_back_to_building.png` |
| 真实浏览器：悬停命中床位 | 通，射线命中 `C-101-01（已入住）` | `v3f_06_hover_a.png`，悬停卡片文本经 DOM 读取确认 |
| 真实浏览器：WebGL 上下文 | 通（canvas 926×520，`webgl` 可用） | 页面内 `eval` 读取 |
| 真实浏览器：100 次快速模式切换 | 通（`fired:100`），场景无「半层楼」残留 | `v3f_09_after_stress.png` |
| 真实浏览器：`visibilitychange` 恢复分支 | 通，恢复后渲染完整 | `v3f_10_after_visibility.png` |
| 真实浏览器：控制台错误 | **0 error**（仅 `vite connecting/connected` debug 日志） | 每批次 `console` + `errors` |

`errors` 在全部批次中均为空输出。

### 4.1 真实浏览器环境

- 隔离 MySQL 实例 `127.0.0.1:3307`（`--no-defaults`）、后端 `127.0.0.1:8000`（`/health` 200）、
  前端 dev server `127.0.0.1:5173`。
- 账号 `admin/admin123`（ADMIN），页面数据为「业务系统数据 + 模拟空间布局」。
- 悬停与可见性场景用页面内派发 `PointerEvent` / `visibilitychange` 触发
  （agent-browser 的鼠标坐标在整页截图下与视口存在偏移，故改由画布自身
  `getBoundingClientRect()` 换算落点，并用悬停卡片文本反证命中）。
- 100 次切换通过 `eval` 连点模式按钮完成，等价于人手快速切换的帧压力。

## 5. 本机守卫脚本相对交付版的差异（断言更强的 2 条）

1. **遮挡目标必须能回退到 `props.selectedId`** —— 交付版 baseline 特性，
   缺它则「选中态过渡更新」是空转（§3.1）。
2. **`visibilitychange` 必须成对注册与反注册** —— 本机是新增监听，
   只加注册漏加反注册会在组件卸载后留下悬挂监听（§3.2）。

另加 6 条回归护栏断言，确保本轮不会顺手删掉 V2/V3 的既有渲染加固
（阴影手动重算、床位基色/悬停色传入、拾取体跟随筛选、遮挡构造逐对象克隆）。

## 6. 遗留与边界

- 本报告与守卫脚本均**只覆盖源码不变量与真实浏览器行为**；
  三维里的房间/床位坐标仍是**模拟排布**，不是 BIM，也不是真实平面图（页面上有声明）。
- `frontend/e2e/smoke.spec.ts`（Playwright）本轮仍未核对：CI 不含 Playwright，非阻塞。
- 交付方包内的 `UIUX_FOLLOWUP.patch` 不会作为补丁文件入库，仅作追溯。
- 未推送远程；未调用任何付费模型。

## 7. 收尾

- 集成提交紧随基线 `281569e`（本轮 commit 见仓库 `main` 顶端）。
- 回滚方式：`git checkout 281569e -- frontend/src/components/WardScene3D.vue`
  （本次只改这一个源码文件；新增的守卫脚本与截图可直接删除）。
