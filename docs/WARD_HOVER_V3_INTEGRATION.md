# Ward Map Hover Visual V3 集成记录

日期：2026-10-15
提交：`281569e`（检查点，落于 follow-up 补丁合并之前）
上游：交付方 Ward Map Hover V3 + Product Polish 候选版（候选 HEAD `7017658`）

本文件补齐 `frontend/verify_hover_visual.cjs` 所引用的集成记录。

---

## 1. 范围

| 文件 | 改动 |
| --- | --- |
| `frontend/src/components/WardScene3D.vue` | 悬停视觉重做（视线探测淡化遮挡 / 床位过阻尼弹起 / 逐床克隆材质） |
| `frontend/src/modules/ward-map/hover-visual.ts` | **新增**：仅场景使用的五态配色与动画参数 |
| `frontend/src/views/WardMapView.vue` | 页面内色块统一取 `sceneBedPalette`，与 3D 所见一致 |
| `frontend/verify_hover_visual.cjs` | **新增**：离线确定性回归（10 条） |
| `frontend/verify_v2_layout.cjs` | **新增**：V2 布局映射回归 |
| `scripts/dev.ps1` | **新增**：三件套幂等启停（`status|up|down|restart` × `all|db|backend|frontend`） |

## 2. 与交付候选版的本地适配（均不改变渲染语义）

1. 类型与布局引用改走 `@/modules/ward-map/*`（本仓库模块路径约定）；
2. 画布改用**透明背景**（`alpha`），底色交给状态图页面的设计令牌渐变，
   明暗主题自动跟随；
3. 新增 `dark` 属性：暗色主题下下调曝光，避免白色病房在深色底上刺眼；
4. 保留 V2 的方向光软阴影（阴影贴图仅在场景/楼层变化时重算）与患者几何加固；
5. **修掉交付版漏传 `surfaceRest` / `surfaceHover` 的运行时缺陷** ——
   `BedVisual` 接口声明了这两个字段，但 `selectable.set()` 未赋值，
   动画循环读到 `undefined` 会抛 `TypeError`；
6. 拾取体仍挂在**楼层 Group**（不随床体浮起移动），因此必须**单独**跟随
   `visibleIds` 隐藏，否则被筛掉的床仍能被射线命中并点开抽屉。

配色边界（重要）：`sceneBedPalette` **只**服务 3D 场景与 `/ward-map` 页面内的
图例/统计/悬停卡；后端五态与全系统统一状态色 `typesMeta` 未改动，
床位管理页徽标不受影响。红色系在场景里表示「不能直接分配」（预占/已入住），
黄色**只**是空闲床的悬停提示色，不代表任何业务状态。

## 3. 验证

| 项 | 结果 |
| --- | --- |
| `node verify_hover_visual.cjs` | 10/10 PASS（含「高频 100 次切换后颜色/透明度可恢复」） |
| `node verify_v2_layout.cjs` | PASS（44 张合成床 / 3 层 / 映射稳定） |
| 真实浏览器 | 见 `docs/screenshots/v3_*.png`（50 张，覆盖整栋剖面 / 单层聚焦 / 分层展开 / 悬停遮挡 / 明暗主题 / 二维列表 / 移动端 390 宽） |

> 上述 `v3_*.png` 由本检查点阶段在真实 Chromium WebGL 下采集。
> 后续 follow-up 补丁的复验证据见
> `docs/UIUX_WEBGL_TRANSITION_FOLLOWUP_INTEGRATION.md`（`v3f_*.png`）。

## 4. 遗留

- `frontend/e2e/smoke.spec.ts`（Playwright）未核对：CI 不含 Playwright，非阻塞。
- 空间坐标仍是后端 `SIMULATED_GRID_V1` 的**模拟排布**，不是 BIM / 真实平面图
  （页面上有醒目声明）。
