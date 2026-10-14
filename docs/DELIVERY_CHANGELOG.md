# P0 / M1 新增代码改动清单

## 来源

WorkBuddy 提供的 REVIEW_SOURCE.zip（README 中为 HEAD 46af053；用户随后报告前端已有 c91f5ad）。本包后端以 REVIEW_SOURCE 为基线再叠加 ChatGPT M1 v0.5，然后追加修复；不能假设已经覆盖用户本地 HEAD。

## 后端改动

| 文件 | 变更 | 风险 |
| --- | --- | --- |
| `models/allocation.py`、`models/__init__.py`、Alembic 新迁移 | G5 双唯一分配 + G6 幂等模型 | 高（需要 MySQL 迁移） |
| `services/allocation.py`、`api/v1/allocations.py`、`schemas/allocation.py`、`core/errors.py` | 申请优先锁、幂等、原子换床、成对校验 | 高（重要业务） |
| `api/v1/allocations.py` | G1 状态日志联表补床号/操作人 | 低 |
| `api/v1/admissions.py` | G3 可用患者姓名检索，响应保持脱敏 | 低 |
| `api/v1/audit.py` | G4 时间范围筛选 | 低 |
| `api/v1/queue.py` | G7 优先级 5→1、同级序号排序 | 中（队列体验变化） |
| `services/recommendation.py` | 修复成本敏感度反向公式；五维权重、其他分值未变 | 中（推荐分数会改变） |
| `seed.py` | 避免 M1 幂等表在演示数据 reset 后残留悬空记录 | 中（只影响破坏性 demo reset） |
| `tests_m1_local/` | SQLite 顺序、API、评分、重置安全单测 | 测试专用 |

## 明确没有完成的事

- **不宣称**原仓库 44 项测试与 MySQL 并发在本环境通过。
- **不宣称**此 Vue 候选版已经构建/浏览器验收；依赖无法获取。
- **不宣称**原 WorkBuddy 最新前端已被审查；来源 ZIP 不含前端。
- 评分「轻症距离越远越好」仍是用户尚待讨论的启发式政策，未在此改变。
- 没有接入 AI、真实 HIS、真实支付或任何真实患者资料。

## 合并时严守的顺序

对照 diff → 对测试库进行迁移与回归 → 备份演示库并查活动记录 → 在本地演示库迁移 → 完整浏览器端到端验证 → 本地 commit，NO PUSH。
