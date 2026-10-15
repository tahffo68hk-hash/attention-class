# UI/UX Deep Polish Final Gate（交付方原文 · 环境受限）

> **收录说明（本仓库）**：本文是交付包
> `Attention_UIUX_WebGL_Transition_Followup_20261015` 中
> `FILES/docs/UIUX_DEEP_POLISH_FINAL_GATE.md` 的**原文照录**，
> 用于追溯交付方在「候选环境」下给出的门禁结论。
>
> 该结论（`BLOCKED`）的成因是交付方环境**访问不到本机 Windows `E:` 仓库、
> 也没有 `node_modules`**（`npm install` 因 `EAI_AGAIN` 失败），
> 因此无法做类型检查、构建与真实 WebGL 验收 —— 这些限制**不适用于本机**。
>
> 本机已完成真实 Chromium WebGL 验收与生产构建，实际门禁结论与本机证据见
> `docs/UIUX_WEBGL_TRANSITION_FOLLOWUP_INTEGRATION.md`。

---

**Decision: `UIUX_DEEP_POLISH_FINAL_GATE=BLOCKED` for the user's Windows production-development checkout.**

Date: 2026-10-15.

## Scope / evidence

- User-specified target: `E:\Attention is all you need` — **not mounted or accessible** in this environment. Therefore neither Windows Git HEAD nor its working tree, native pre-change pages or local test environment can be verified or modified here.
- Accessible source: prior independently prepared **Ward Map Hover V3** + Product Polish candidate at `/mnt/data/attention_uiux_verified_candidate`, with base HEAD `7017658` (the earlier code and documentation commits were `ea04a14` and `7017658`).
- Browser Chromium is installed, but this candidate has no project `node_modules`; attempted `npm install --ignore-scripts --no-audit --no-fund --fetch-retries=0 --fetch-timeout=5000` failed with `EAI_AGAIN registry.npmjs.org` when requesting `@playwright/test`.
- Thus **no Vue typecheck, Vite production build, real Vite/Three.js WebGL screenshot, live API or native Windows integration result is claimed**. Screenshots marked Before/After from that environment do not exist.

## This incremental candidate improvement

1. During multi-floor movement, re-evaluate occlusion for **selected beds even without current hover**. This avoids stale translucent floors/walls during an ongoing focus transition.
2. Before calculating occluder intersections, update Three.js world matrices for both the root scene and camera so raycasts use current floor/bed transformations, not the previous rendered frame.
3. On `document.hidden`, cancel camera and floor transition RAFs as well as bed-effect RAFs, and do not reschedule hidden-tab effect frames. On visibility restoration, complete interrupted floor mode coherently and re-focus the selected bed, if any.
4. Added `verify_webgl_transition_guards.cjs` to exercise focused structural regression guards in the candidate. These tests verify source invariants **only** and are not a simulated claim of genuine 3D interaction.
5. Other existing modules, medical statuses, algorithms, DeepSeek provider, DB schema, and business logic remain untouched.

## Test record

| Test | Status | Meaning |
| --- | --- | --- |
| `node verify_hover_visual.cjs` | 9/9 PASS | Static and pure-module Hover checks |
| `node verify_v2_layout.cjs` | PASS | 44 synthetic beds / 3 floors; stable mapping |
| `node verify_product_polish.cjs` | 16/16 PASS | Static and pure-module product UI checks |
| `node verify_webgl_transition_guards.cjs` | 9/9 PASS | Selected occlusion, matrices and hidden-frame guards |
| `git diff --check` | PASS | Whitespace / patch checks |
| `npm install` | BLOCKED (EAI_AGAIN) | Package registry DNS unavailable; no dependencies installed |
| `vue-tsc --noEmit` / `vite build` | NOT RUN | Dependencies unavailable |
| Actual Chromium WebGL incl. hovering, transparency restore, floor transitions | NOT RUN | Vue/Three.js unavailable at runtime |
| Windows Before/After screenshots | NOT AVAILABLE | Windows source and running services inaccessible |
| Native Windows Git commit | NOT POSSIBLE | `E:` not mounted |

## Windows final Gate still required

1. Read actual Windows `git rev-parse HEAD`, `git status --short` and check version of `WardScene3D.vue` before merging. Do not overwrite P3/P4, V3, security or later fixes.
2. Capture real **Before** screenshots at equivalent camera, data and viewport. Merge only missing changes from the separate candidate patch.
3. Run actual `vue-tsc`, Vite build and live Chromium WebGL tests for five statuses, hover/lift/recovery, selected occlusion during camera/floor motion, 100 rapid switches, picker filters, drawers, keyboard, reduced motion and mobile fallback.
4. Capture true **After** screenshots, JS console errors, and project-specific API and UI tests. Do not call a billable DeepSeek model.
5. Close real defects, commit in the Windows local repo (NO PUSH), ensure the worktree is clean, and only then update `UIUX_DEEP_POLISH_FINAL_GATE=PASS` with actual evidence.

This record intentionally does **not** assert production completion based on offline tests.

---

## 本机对照（Windows `E:\Attention is all you need`）

交付方上面第 1–5 条「Windows final Gate still required」在本机的落实情况：

| 交付方要求 | 本机状态 |
| --- | --- |
| 1. 先读实际 `git rev-parse HEAD` / `git status`，不覆盖更新的修复 | 已做：先落检查点 `281569e`，再逐处语义合并（未整文件覆盖） |
| 2. 真实 Before 截图，只合并缺失改动 | 已做：`v3f_01_building.png`（合并后基线）+ 逐处语义存在性检查 |
| 3. `vue-tsc` / Vite build / 真实 Chromium WebGL | 已做：类型检查 0 错误、构建成功、真实浏览器 10 张截图、100 次快速切换 |
| 4. 真实 After 截图 + console errors + 项目测试 | 已做：`v3f_02`–`v3f_10`，`errors` 全批次为空 |
| 5. 本地提交（NO PUSH）、工作树干净、再置 PASS | 见 follow-up 报告 §4 / §7；未推送 |
