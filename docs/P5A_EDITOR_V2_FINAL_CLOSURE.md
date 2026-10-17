# P5-A Editor V2 Final Closure —— 收口验证报告

基线：`cae5da6`（`feat(ward-map): 集成槽位式沙盘 V2`），分支 `main`，起始工作树**干净**
（`git status --porcelain` 空）。
本轮**没有修改任何产品源码**：只跑闸门、做真实浏览器验收、归档验收脚本与截图。
结论：**EDITOR_V2_FINAL=PASS**（唯一未闭环项仍是演示库迁移，见 §七）。

---

## 一、四项功能实际完成情况

| # | 要求 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | 槽位式沙盘 V2 已集成：地面固定槽位 / Ghost / 点击放置 / 移动 / 移除 / 撤销重做 / Esc 取消 | **已完成** | 真实 Chromium 逐项操作，见 §三；`WARD_SLOT_SANDBOX_V2 19/19 PASS` |
| 2 | 真实 Chromium WebGL 验证以上操作，含床位状态、遮挡恢复、槽位不重叠 | **已验证** | §三、§四（像素级 hover/restore 对比 + 五种状态悬停） |
| 3 | 模拟增减床位后由现有服务重算 Greedy / exact_min_cost_flow，且不写真实业务数据 | **已验证** | §五（面板 + API 双路径；四张业务表计数前后完全一致） |
| 4 | 正式床位新增 / 停用 / 恢复通过隔离 MySQL 迁移、权限、事务、并发测试 | **已通过** | `tests/test_ward_editor_mysql.py` 8 项 + `test_ward_editor_migration.py` 1 项，全绿 |

## 二、复用与新增的闸门

**后端（隔离 MySQL `hospital_test`，本轮重跑）**

```
pytest -q tests tests_ward_map  ->  87 passed, 1 warning in 87.46s
  tests/test_ward_editor_mysql.py ........   (8)  正式床位 CRUD / 权限 / 事务 / 并发
  tests_ward_map/test_ward_editor_migration.py .  (1)  迁移回填保留真实 id 与唯一槽位
  tests_ward_map/test_ward_editor.py ......  (6)  含 synthetic 供给走 exact 求解器且零写入
```

用例数 87（≥ 前一轮的 79 项口径，全部仍适用，故未删减）。
`conftest.py` 在建表前先 `DROP TABLE` 全部表，再用 `alembic upgrade head` 从零建表 ——
**迁移脚本本身每轮都在被验证**，且强制库名必须是 `hospital_test`。

**前端（本轮重跑）**

| 闸门 | 结果 |
| --- | --- |
| `verify_ward_slot_v2.cjs` | 19/19 PASS |
| `verify_ward_editor_next.cjs` | 30/30 PASS |
| `verify_ward_editor.cjs` | 23/23 PASS |
| `verify_hover_visual.cjs` | 10/10 PASS |
| `verify_reduced_motion_parity.cjs` | 12/12 PASS |
| `verify_webgl_transition_guards.cjs` | 17/17 PASS |
| `verify_v2_layout.cjs` | V2_LAYOUT_GATE PASS（44 bed / 3 floor） |
| `verify_spatial_simulation.cjs` | SPATIAL_LAYOUT PASS + SANDBOX_CONTRACT_TS PASS |
| `vue-tsc --noEmit` | exit 0（0 行输出） |
| `vite build` | `✓ built in 5.22s`，`WardMapView 619.85 kB`（three.js 历史体积，无新增告警） |

## 三、真实 Chromium WebGL 验收（编辑器交互）

环境：`127.0.0.1:5173`（Vite dev）+ 真实 headless Chrome（agent-browser 0.38.1，viewport 1440×960）
+ `127.0.0.1:8000` 后端（**当前源码**，指向 `hospital_test`）。

落点方式：页面内用 `getWorldPosition().project(camera)` 求槽位投影，再用组件自身的
`pickSlot()` 反查落点，**逐点确认命中的就是目标瓦片**（偏移 off=0），然后派发真实
`pointerdown / pointerup / click` 到 WebGL canvas。探针只存在于页面内存，未写入源码。

| 操作 | 实测结果 |
| --- | --- |
| 地面固定槽位 | C-101 显示 `S01–S12`，编号在整页截图可读；`44 正式床 · 0 模拟床 · 当前病房 8 空槽` |
| Ghost 预览 | 悬停空槽 S05 → 瓦片高亮 + 半透明绿色 Ghost 床位同时出现 |
| 点击放置 | 点 S05 → `SIM-001 已放置到 S5`，计数变 `1 模拟床 / 7 空槽`，S05 转「模拟占用」 |
| **槽位不重叠** | 放置工具再点同一槽位 → 红字 `已有模拟床位`，**计数未变**；面板槽位无重复（`duplicateSlots=false`） |
| 移动 | `↔ 移动` → 点模拟床（选中）→ 点 S06 → `已移动至 S6`，模拟床数仍为 1，S05 回落空槽 |
| 移除（模拟床） | `− 移除` 点模拟床 → `已移除 SIM-001`，回落 `0 模拟床 / 8 空槽` |
| **移除（正式床）** | `− 移除` 点正式床 C-101-01 → `正式床位不能在模拟沙盘中直接删除；请使用 What-if 临时禁用`，计数不变，**未发任何正式 DELETE** |
| 撤销 / 重做 | 撤销 → 模拟床回到 S06；重做 → 再次清空；提示分别为「已撤销 / 已重做」 |
| **Esc 取消** | `＋ 放置` 后按 Esc → 工具回到「查看」（`aria-pressed` 只落在查看上） |
| 右键取消 | 画布 `contextmenu` → 工具同样回到「查看」 |

合成床 id 恒为负（`Math.min(0,…)-1`），除「调度沙盘」按钮走既有只读优化接口外，编辑器全程零业务写入。

## 四、床位状态 / 遮挡恢复 / 槽位不重叠

**五种状态**（逐个悬停真实床位，`pointermove` 命中后读取提示）：

| 状态 | 实测床号与提示 |
| --- | --- |
| 空闲 | `C-101-02 ● 空闲 · 心内一病房 · 暂无活动分配记录` |
| 预占用 | `C-ICU-01 ● 预占用 · 心内监护单元 · 关联患者 周* · 急症` |
| 已入住 | `C-101-01 ● 已入住 · 心内一病房 · 关联患者 张* · 重症` |
| 清洁中 | `P-201-01 ● 清洁中 · 儿科一病房` |
| 维护中 | `R-202-04 ● 维护中 · 呼吸二病房` |

页面统计卡同步为 `44 总 / 37 空闲 / 2 预占 / 3 入住 / 1 清洁 / 1 维护`。

**遮挡淡化与恢复（像素级）**：同一机位截三帧 —— 基线 / 悬停 / 离开。

```
baseline -> hover   changed_px=46,231  ratio=0.0334  bbox x[793,1100] y[689,902]
baseline -> restored changed_px=0      ratio=0.0000
hover    -> restored changed_px=46,231 ratio=0.0334
```

即：悬停只改变床位邻域 3.3% 的像素（高亮 + 楼板/墙体让路），**移开后与基线逐像素完全一致**，
没有残留半透明楼板或残留高亮。

**槽位不重叠**由两层共同保证：面板 `listFloorSlots()` 对同房同槽直接抛
`病房 X 存在重叠槽位`；`validatePose()` 再次拒绝已占槽位；运行时表现为「已有模拟床位」并被计数否决。

## 五、沙盘供给 → 现有求解器，零写入

**面板路径（真实浏览器）**：编辑器放 1 张模拟床 → `◇ 用当前编辑草稿重新计算调度（只读）`
→ 选「心血管内科」→ `+ 添加虚构申请` → `重新计算模拟方案`：

```
编辑器供给变化：模拟新增 1 张，临时移除空闲床 0 张
模拟安排人数 1/1 · 优先级和 2 · 评分合计 88.24
exact_min_cost_flow · 已证明该模拟目标最优 · 零写入
模拟 #1 → C-102-04（88.24）
切到 Greedy 页：greedy · 启发式方案，无最优性保证 · 零写入
```

**API 路径（同一后端、同一接口）**：

```
baseline : greedy=greedy admitted=1 | optimized=exact_min_cost_flow admitted=1 proven_optimal=True
supply+1 : 同上，候选含 SIM-001（虚拟 id=-1）
supply-1 : applied_unavailable_bed_ids=[2]
表计数 before/after：beds 44 / bed_scene_slots 0 / bed_allocations 6 / admission_requests 16 / preadmissions 14
IDENTICAL: True
```

即「加减供给」没有新写评分逻辑，走的仍是 `preview_sandbox` → 既有 H1–H4 硬约束 + 五维权重 +
`greedy` / `optimize(backend='flow')`，且**不落库**。

> 上一轮记录的「headless 下科室 `<select>` 选不中导致沙盘跑不出结果」在本轮已消除：
> 用原生 `selectedIndex + change` 事件驱动即可正常求解，属测试手法问题，未改产品代码。

## 六、正式床位管理（隔离 MySQL）

`tests/test_ward_editor_mysql.py`（8 项，本轮全绿）覆盖：

- `test_lifecycle_and_audit_on_mysql` —— 新增 → 停用 → 恢复全链路 + 审计
- `test_archive_denied_for_non_free_status_on_mysql` —— 非空闲床拒绝停用
- `test_slot_conflict_is_rejected_without_partial_write` —— 槽位冲突**整体回滚**，无半写
- `test_concurrent_create_same_slot_serializes_via_row_lock` —— `SELECT … FOR UPDATE` 串行化
- `test_non_admin_cannot_touch_managed_beds` —— 非 ADMIN 403
- `test_admin_can_create_and_unknown_bed_is_404` —— 权限放行 + 未知床位 404
- `tests_ward_map/test_ward_editor_migration.py` —— 迁移回填保留真实 id、房内槽位唯一

演示库 `hospital` 本轮**未做任何写入**：`beds 44 / bed_allocations 23 / admission_requests 22`、
`alembic 9bca1026e001`、`audit_logs` 最后一条时间戳仍早于本轮开始。

## 七、未完成 / 遗留（如实记录）

1. **演示库 `hospital` 仍未迁移**（既有阻塞，非本轮引入）：`alembic 9bca1026e001`，缺
   `bed_scene_slots`。当前源码直连演示库会在 `GET /api/v1/ward-map` 报
   `Table 'hospital.bed_scene_slots' doesn't exist`（500）。
   按项目约定**迁移须先取得授权**，本轮未执行。因此 §三–§五 的浏览器证据跑在
   `hospital_test`（已迁移到 `20261015ed02`，同样是虚构演示数据）上。
2. **8000 端口原进程是旧代码**（39 路径、`WardSandboxInput` 无 `synthetic_beds`，
   沙盘带合成床会 422）。本轮已将其停掉，改用当前源码重启（44 路径、含 `synthetic_beds`），
   但**指向 `hospital_test`**；会话结束后该进程可能随沙箱回收。
   恢复演示库前请先授权迁移，否则 `dev.ps1` 起来后 ward-map 仍会 500。
3. **整栋剖面下的瓦片遮挡**（观察，非缺陷）：全楼层瓦片同时可见时，正交投影下上层瓦片会挡在
   下层瓦片前方，点击命中最靠近相机的瓦片（`pickSlot` 会正确跳过隐藏楼层，但不会跳过可见的上层）。
   单层聚焦下逐点 `pickSlot` 反查偏移为 0，落点精确。是否要在整栋模式加「楼层过滤」属产品取舍，
   本轮未改代码。
4. 未做：演示库迁移、Alembic 新迁移（本轮无 schema 变化）、旧交付包三方合并、无关全量审计。

## 八、最少必要截图

| 文件 | 说明 |
| --- | --- |
| `docs/screenshots/p5a_02_editor_slots.png` | 12 个地面槽位 S01–S12 + 面板计数 |
| `docs/screenshots/p5a_03_ghost_green_zoom.png` | 悬停空槽 S05：瓦片高亮 + 绿色 Ghost |
| `docs/screenshots/p5a_04_placed_zoom.png` | 放置后 S05 变成模拟床（青色槽位 + 新床） |
| `docs/screenshots/p5a_05_overlap_rejected.png` | 同槽位再放 → 红字 `已有模拟床位` |
| `docs/screenshots/p5a_06_moved.png` | 移动后 S05 空、S06 模拟床 |
| `docs/screenshots/p5a_07_remove_real_rejected.png` | 移除正式床被拒（含完整文案） |
| `docs/screenshots/p5a_08_undo_restored.png` | 撤销恢复 |
| `docs/screenshots/p5a_09_esc_cancel.png` | Esc 后工具回「查看」 |
| `docs/screenshots/p5a_10_sandbox_recompute.png` | 草稿供给 +1 → `exact_min_cost_flow · 已证明最优 · 零写入` |
| `docs/screenshots/p5a_11_sandbox_greedy.png` | 同结果切 Greedy 页 |
| `docs/screenshots/p5a_13_hover_bed.png` / `p5a_14_hover_restored.png` | 悬停 / 离开恢复（像素差 0） |
| `docs/screenshots/p5a_15_status_hover.png` | 五态悬停（清洁中 → 维护中） |

## 九、验收脚本（可复跑）

`frontend/verify_p5a/`：`helpers.py`（batch 驱动 + JS 预校验）、`browser_editor.py`、
`browser_sandbox.py`、`browser_hover.py`、`browser_status.py`、`sandbox_supply_api.py`。
运行前提：5173 dev server、8000 后端（当前源码）、可用的 agent-browser 与隔离 MySQL。
