# Attention is all you need — P1/P2 增量优化 v1.1（2026-10-14）

## 范围与事实

基于 `Attention_is_all_you_need_P1_P2_Full_Source_20261014.zip`，本轮仅修复既有 P1 多患者预览、P2 解释与相关纯算法输入校验。不替换 WorkBuddy 最新 Windows 本地仓库，不自动批量分配，不修改 M1 的 MySQL 迁移、分配事务、五维评分或五态床位。

## 完成的修复

1. **P2 解释完整候选集**：`recommend_beds(..., limit=None)` 允许内部获取全部合规床位。`explain()` 不再因请求的合法床位排在前 101 名外就误报硬约束失败。
2. **P2 有效申请条件**：仅允许已预登记、`PRE_ADMITTED` 且没有 `RESERVED/ADMITTED` 有效分配的住院证获取正向解释。已经入住、出院或取消的申请不会被描述为仍可分配。
3. **P1 显式容量限制**：优化预览读取全部候选后，再判断是否超过单申请 100 张床。超量时返回 422，而不是静默截断后宣称全局最优。
4. **P1 自动求解确定性**：`solver=auto` 使用已验证的精确最小费用流，避免 OR-Tools 安装状态意外影响响应时间；仅 `solver=cp_sat` 会调用可选 CP-SAT（必须求得 OPTIMAL，否则显式报错）。
5. **输入域校验**：`True/False` 不再可作为床位 ID、申请 ID 或评分。
6. **测试补齐**：56 项本地测试通过，包括新增长列表、活动分配、不合法状态、小数最优性等边界案例。

## 本轮实际验证

- `cd backend && python -m pytest -q tests_m1_local tests_p1p2`：**56 passed**（2.95 s，本轮容器环境）
- `cd backend && python -m compileall -q app`：通过
- FastAPI OpenAPI：**36** 条路径，优化预览和两个解释路径存在
- 改动范围：`backend/app/services/{recommendation.py,global_optimization.py,optimization_preview.py,assistant_explanation.py}`，以及 P1/P2 的两个测试文件
- 正式项目 MySQL 44 项回归、真实并发、npm 全量构建、浏览器和 Docker：**未在当前环境执行**

## 集成边界

- 此包基于上一轮 **P1/P2 Full Source 20261014**，增量补丁必须在该代码基线上试应用；它 **不是** 针对 WorkBuddy 最新 Windows `E:\Attention is all you need` 的直接覆盖补丁。
- 优先使用 `P1_P2_OPTIMIZATION_V11.patch` 或手工比对六个修改文件进行增量合并；不要覆盖已验收的 WorkBuddy 前端与其之后的提交。
- 不需要数据库迁移；无真实 AI API 调用，`ASSISTANT_EXTERNAL_ENABLED` 继续保持禁用。
- WorkBuddy 在独立 `hospital_test` 中验证原 44 项及新增测试；原测试夹具可能重建测试库表，先确认数据库隔离。不得把测试指向演示/生产库。
- 本地 Git commit 允许，NO PUSH。
