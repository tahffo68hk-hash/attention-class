# 明天发给本地 Agent 的简洁交接指令

在 `E:\Attention is all you need` 里，以现有 Git 工作区为准，对照本 ZIP 内的 `BACKEND_DELTA.patch`、`docs/DELIVERY_CHANGELOG.md` 和 `backend/` 做增量集成。

1. 先检查有无未提交的文件与最新 HEAD；本包来源后端是较早的 REVIEW_SOURCE，不要盲目全目录覆盖。
2. 优先合入 M1 v0.5 的 G5/G6/原子换床及迁移，再合入新增的 G1/G3/G4/G7/成本敏感度修复和测试。**不要替换五态床位或五维评分框架。**
3. WorkBuddy 已有前端则保留现有页面；此包 `frontend/` 是 ChatGPT 独立写的候选实现，只挑对现有前端有益的功能/组件增量合并（例如换床入口、幂等、时间筛选），不要覆盖原有前端。
4. 先在确认可清空的独立 hospital_test 跑测试（conftest 会 DROP/recreate 所有测试表），并运行原有 MySQL 并发测试；成功后备份演示库、查活动重复分配，再迁移演示库。
5. 运行 Vue 类型检查与构建、浏览器完整写入闭环，发现错误优先修第一条可操作错误，直到验证或确有环境阻塞。保留测试真实输出和截图。
6. 本地 Git commit，NO PUSH。报告迁移、测试数、主要差异、Git hash、真实阻塞。不要接入真实医疗或收费系统。
