# 本地集成 Gate（由 WorkBuddy/用户在 Windows 执行）

## 一、源码交接

1. 保留 `E:\Attention is all you need` 当前 Git 状态，先用 `git status` 检查修改；不要复位或覆盖 WorkBuddy 已完成前端。
2. 对照此包中的 `P1_P2_DELTA.patch` 合入新增 `backend/app/services/global_optimization.py`、`optimization_preview.py`、`assistant_explanation.py`、schemas、API 路由、测试、前端新增页面及菜单。由于差异基线是 ChatGPT 上轮 P0/M1 候选包，**不能保证直接应用到 Windows HEAD**；先用 `git apply --check`，失败时按文件人工合并，保留 M1 修复。
3. 默认保持 `ASSISTANT_EXTERNAL_ENABLED=false`，没有新授权不得设置真实 API Key 或触发模型请求。

## 二、本地验证次序

- Python：先 `pytest -q tests_p1p2 tests_m1_local`；之后在独立 `hospital_test` 上执行既有 `pytest -q tests`。注意 `tests/conftest.py` 会 DROP 并重建测试表，不得指向演示库或生产库。
- `python -m compileall -q app`；FastAPI `/docs` 应出现 `/api/v1/optimization/preview`、`/api/v1/assistant/explain` 和 `/api/v1/assistant/explain-plan`。
- `npm install && npm run build`，再打开浏览器验证：全局排床选择多患者→比较→显示匹配与未匹配→跳到推荐页；辅助解释选择合格床位→规则说明→模型标签为非 AI。
- 后端真实 MySQL 并发：继续验收单床位/单住院证唯一活动分配、换床原子性和幂等；P1 计划展示不得改变活动分配表记录数。
- 真实模型默认关闭：尝试 `mode=llm` 无确认时返回 403，有确认但服务端未启用仍返回 403，真实外部请求次数为 0。
- 需要演示数据时，必须先确认可清空库；`seed.py` 会修改演示数据，不能误运行到 `hospital_test` 或未备份的含保留数据的库。
- Docker Compose、前端生产构建与浏览器实测在本轮对话环境均不能代表 Windows 现场验收。通过以后才可提交本地 Git（NO PUSH）。

## 三、报告时提供

实际 Git HEAD、迁移结果、原有 MySQL 回归数、P1/P2 新增测试数、真实 MySQL 并发结果、前端构建与浏览器截图、两个方案的实测指标、遗留失败项。不要把未测过的项写为 PASS。
