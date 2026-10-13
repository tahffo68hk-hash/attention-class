# 文档索引

| 文档 | 内容 |
| --- | --- |
| [architecture.md](./architecture.md) | 系统架构、模块划分、技术选型、目录结构 |
| [er-diagram.md](./er-diagram.md) | 数据实体 E-R 图（含外键、索引、状态约束说明） |
| [business-flow.md](./business-flow.md) | 住院证 → 预入院 → 推荐 → 分配 → 出入院 的业务流程图 |
| [recommendation-algorithm.md](./recommendation-algorithm.md) | 床位推荐核心算法：硬约束过滤 + 可解释软约束评分 |
| [isolation-bed-policy.md](./isolation-bed-policy.md) | 隔离床使用策略（显式文档化） |
| [m0-checklist.md](./m0-checklist.md) | M0 工程初始化的交付项与验收结果 |

> **状态说明**：`er-diagram.md` 与 `recommendation-algorithm.md` 中描述的业务表结构、
> 状态机与评分权重均为**原型草案**，用于跑通端到端演示，尚未经过业务方确认；
> 正式设计将在评审后定稿。M0 阶段交付的是工程骨架与基础设施。
