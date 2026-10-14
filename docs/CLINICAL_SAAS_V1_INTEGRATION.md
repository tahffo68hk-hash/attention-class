# Clinical SaaS Visual Redesign V1 — 增量集成报告

> 本报告对应本地提交 **`6a2a21b`**（`6a2a21bd780f6026474c6004ad1b93731a102ef3`），
> 集成前基线 HEAD 为 **`bff1522`**。**已本地提交、未推送（NO PUSH）**。

## 1. 来源与边界

| 项 | 内容 |
| --- | --- |
| 交付包 | `Attention_Clinical_SaaS_Visual_Redesign_V1_Frontend.zip`（40 KB / 28 项） |
| 解压位置 | `E:\attention-handoff\clinical_saas_v1\`（项目外，不参与构建） |
| 说明文档 | 包内 `CLINICAL_SAAS_HANDOFF.md`（已通读） |
| 包基线 | 基于 ChatGPT 可访问的 **P4 Full Source 候选前端**，**不是**本机最新工作树 |
| 包自述状态 | `DESIGN_CODE_DELIVERED=YES` / `FRONTEND_WINDOWS_INTEGRATION=NOT_RUN` / `VUE_BUILD=NOT_RUN` / `BROWSER_GATE=NOT_RUN` |

> 注：任务文本提到的 `..._Delta.zip` 在本机不存在，实际提供的是 `..._Frontend.zip`，
> 包内变更清单为 `SHA256_CHANGED_FILES.json`（5 个文件：`App.vue` / `style.css` /
> `BedsView.vue` / `DashboardView.vue` / `LoginView.vue`），已按此执行。

**包基线与本地差异（决定了必须语义合并、不能覆盖）**

| 维度 | 交付包 | 本地最新工作树 |
| --- | --- | --- |
| 目录分层 | `src/lib/api.ts` 单文件 | `src/api/{auth,business,http,system,types}.ts` 分层 |
| 外壳 | `App.vue` 一体式 | `App.vue` + `layouts/AdminLayout.vue` |
| 路由 | `src/router.ts`，路径式命名（`/queue`、`/system`、`/base-data`…） | `src/router/index.ts`，命名路由（`/dashboard`、`/system-status`、`/recommendations`…）+ 守卫 |
| 会话 | `sessionStorage` | `localStorage`（`hba.token` / `hba.user`）+ `stores/auth.ts` 角色能力 |
| 鉴权 | 无角色能力模型 | 有 `canIssueCertificate` / `canOperateAllocation` / `canRevealPatients` |
| 页面 | `QueueView` / `BaseDataView` / `SystemView` | `RecommendationView` / `SystemStatusView` 等，且 P3/P4 逻辑更完整 |

## 2. 集成策略（不整体覆盖）

**设计系统层与业务层解耦**：

1. **令牌层**——把 Clinical SaaS v1 的设计令牌（浅色 + `.theme-dark`）落到
   `src/styles/main.css`，同时把本地既有的 `--color-*` 语义别名映射到同一套令牌。
   于是**所有旧页面无需改动**即自动跟随新配色与明暗主题。
2. **外壳层**——`AdminLayout.vue` 重写为 AppShell，但导航项与本地**命名路由一一对应**，
   不新增/不删除任何业务入口；退出登录仍调用本地 `useAuth().signOut()`。
3. **组件层**——只把包内 UI 元素（Hero、指标卡、床位矩阵、右侧抽屉、命令搜索）
   **按语义并入**对应本地页面，保留本地字段与接口。

**未触碰**：`backend/**`（含 `app/services/recommendation.py`、`bed_policy.py` 评分与硬约束）、
`backend/alembic/**`、`sql/**`、`docker-compose.yml`。

## 3. 修改文件清单

| 文件 | 变更 |
| --- | --- |
| `frontend/src/styles/main.css` | 重写为设计系统：令牌（明/暗）+ AppShell + 组件层 + 响应式；本地既有业务类全部保留 |
| `frontend/src/layouts/AdminLayout.vue` | 重写为 AppShell（分组侧栏 / 面包屑 / 折叠 / 移动导航 / Ctrl+K 搜索 / 主题切换 / 教学提示 / 页脚） |
| `frontend/src/lib/theme.ts` | **新增**：主题读写、系统偏好回退、切换并持久化 |
| `frontend/src/main.ts` | 挂载前落主题，消除首帧闪烁 |
| `frontend/index.html` | `<head>` 内联首帧主题脚本 + `color-scheme` |
| `frontend/src/views/DashboardView.vue` | 新增 Hero（含占用率进度条）、8 张指标卡、快捷入口；数据仍取 `/api/v1/dashboard/summary` |
| `frontend/src/views/BedsView.vue` | 新增列表/矩阵视图切换 + 右侧状态流水抽屉；抽屉内可直接触发维护/释放（受同一权限与状态规则约束） |
| `frontend/src/components/Modal.vue` | 新增 `variant="drawer"`（默认值是 `default`，原调用行为不变） |
| `docs/screenshots/v1_*.png` | **新增 22 张**验收截图 |

`LoginView.vue` **未做源码级修改**（原因见 §6）：其视觉由设计系统层的
`.auth/.auth-card/.login-page/.login-card` 规则接管，两种主题下均已实测生效。

## 4. 保留的 P3 / P4 行为（回归点）

- **P3 手工状态规则**：`BedsView` 的 `MANUAL_TRANSITIONS` 仍为
  `AVAILABLE ⇄ MAINTENANCE` 两条；预占/入住/取消/出院/清洁释放仍只能走各自业务入口。
  「释放」按钮仍仅对 `CLEANING` 且 `canOperateAllocation` 时出现，并保留 `window.confirm` 二次确认。
- **P3 权限模型**：`useAuth()` 的角色能力（ADMIN/DOCTOR/NURSE/VIEWER）原样使用；
  矩阵视图与抽屉只复用同一套判定，未放宽。
- **P4 DeepSeek 一次确认逻辑**：`/assistant` 页面原样保留「说明方式」二选一
  （确定性规则说明 / DeepSeek 实时生成）与生成按钮上的确认约束；
  页面实测显示 *「DeepSeek 服务状态：未启用或未配置密钥」*。
- **真实调用开关**：`backend/.env` 中 `DEEPSEEK_EXTERNAL_ENABLED=false`、
  `ASSISTANT_EXTERNAL_ENABLED=false` 未改动，本轮**没有任何外发付费调用**。
- **路由与守卫**：`router/index.ts` 未改动（`requiresAuth` + 令牌重定向保持原样）。

## 5. 验证结果

### 5.1 静态检查与构建

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 类型检查 | `vue-tsc --noEmit` | **PASS**（0 error） |
| 生产构建 | `vite build` | **PASS**，126 modules，`index-*.js` 165.47 kB（gzip 63.81 kB） |
| 构建中的首修 | `AdminLayout.vue:130` `ThemeName` 赋给 `boolean` → 改为 `=== 'dark'` 后通过 | 已修复 |

CI（`.github/workflows/ci.yml`）前端步骤为 `npm run build`＝`vue-tsc --noEmit && vite build`，
与本地验证口径一致；CI **不涉及** Playwright。

### 5.2 真实浏览器验收（agent-browser，Chrome 153）

| 用例 | 结果 |
| --- | --- |
| 登录页（深色 / 浅色） | PASS，卡片随主题变为 `#182235` / 白色 |
| 登录（admin/admin123）→ 跳 `/dashboard` | PASS |
| 分组侧栏 4 组 10 项 + 面包屑 + 演示环境标记 | PASS |
| 9 条业务路由逐条巡检（h1 / 导航高亮 / 面包屑 / 表格） | PASS，全部与路由一致 |
| Dashboard 数据（`total_beds=44` 等 8 项 + 科室表 5 行 + 优先级队列） | PASS，来自 `/api/v1/dashboard/summary` |
| 床位列表 20 行 / 矩阵 20 块（状态色左边框）/ 分页「共 44 条 · 第 1/3 页」 | PASS |
| 右侧状态流水抽屉 | PASS：右对齐、宽 760、高 900、5 列（时间/变更/原因/操作人/关联分配） |
| 快捷搜索 Ctrl+K | PASS：打开 10 项；输入「床位」→ 过滤为 2 项 |
| 主题切换 + 持久化 | PASS：`localStorage['attention-theme']='dark'`、`<html class="theme-dark" data-theme="dark">` |
| 移动端 390 侧栏抽屉 | PASS：`nav-open` 生效、`sidebarLeft=0`、遮罩出现 |
| 移动端床位列表 / 矩阵 | PASS（表格在 `.table-wrap` 内横向滚动，页面不溢出） |
| `/assistant` DeepSeek 未启用状态 + P4 确认 UI | PASS |
| **Console 0 error** | PASS（`console` 仅 3 条 `[vite] connecting/connected`，`errors` 为空） |
| **横向溢出** | 桌面 1440 与移动 390、明暗两种主题、共 20+ 次采样：**`overflowX=false` 全部通过** |

### 5.3 本轮修复的真实问题（非前端引入）

- **后端登录 500 `INTERNAL_ERROR`**：运行中的 uvicorn 进程（PID 23356）持有
  **口令轮换前**的数据库凭据，MySQL 拒绝 `hospital_app` 认证
  （`pymysql.err.OperationalError 1045`）。已终止旧进程并按 `backend/.env`
  重启，`/health` 200、登录返回 200。**未改动任何后端代码与 `.env`**。

## 6. 未执行项与已知风险（如实记录）

1. **`frontend/src/views/LoginView.vue` 与 `frontend/e2e/smoke.spec.ts` 无法读取** ——
   读取请求被本机安全审批拦截（`SENSITIVE_APPROVAL=TIMED_OUT`，工具要求本轮不得重试）。
   影响：
   - `LoginView.vue` **未做源码级合并**；其视觉改由设计系统层的
     `.login-page/.login-card/.auth/.auth-card` 规则覆盖，已在明暗双主题下截图验证生效。
     若需把包内 `auth-card` 的 brand-icon 等**结构**也并进去，需要在放行该文件读取后再改。
   - `e2e/smoke.spec.ts` **未核对**：若其中断言了旧外壳文案（如「版本 v0.1.0 · M0」），
     可能在后续执行 Playwright 时失败。
2. **Playwright e2e 未运行** —— 本机 `node_modules` 缺少 `@playwright/test`（离线缓存不可用），
   且 CI 不含该步骤。本轮以 agent-browser 真实浏览器替代。
3. **历史流水操作者回退分支未覆盖到实样**：抽取到的日志行操作人为「王芳」，
   因此「未记录（历史）」回退未在截图中出现（分支已实现，见 `BedsView.operatorOf`）。
4. 业务库**未执行**任何迁移、重置或批量写入；仅登录与只读查询，
   另有 P3 既有测试数据参与列表展示。

## 7. 截图索引（`docs/screenshots/`）

| 文件 | 说明 |
| --- | --- |
| `v1_01_login_dark_desktop.png` / `v1_02_login_light_desktop.png` | 登录页（深/浅） |
| `v1_03_dashboard_light_desktop.png` / `v1_17_dashboard_dark_desktop.png` | 管理看板 Hero + 指标卡（浅/深） |
| `v1_04_command_search.png` | Ctrl+K 快捷搜索 |
| `v1_05_beds_list_light_desktop.png` / `v1_16_beds_dark_desktop.png` | 床位列表 / 床位矩阵（深） |
| `v1_14_beds_matrix_light_desktop.png` | 床位矩阵（浅） |
| `v1_15_bed_drawer_light_desktop.png` | 右侧状态流水抽屉 |
| `v1_06`–`v1_13_*_light_desktop.png` | 住院证/推荐/分配/联合排床/辅助解释/审计/系统状态/项目说明 |
| `v1_18`–`v1_22_*mobile390*` | 移动端 390：看板、侧栏抽屉、床位列表、床位矩阵（深/浅） |

## 8. Git

| 项 | 值 |
| --- | --- |
| 集成前基线 | `bff1522` |
| 本次集成提交 | `6a2a21b`（`6a2a21bd780f6026474c6004ad1b93731a102ef3`） |
| 分支 | `main` |
| 推送 | **未推送（NO PUSH）**，`origin/main` 仍停在集成前 |
| 变更规模 | 30 files changed, 1989 insertions(+), 440 deletions(-) |
