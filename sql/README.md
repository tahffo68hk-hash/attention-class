# sql 目录说明

本目录存放**数据库层**的脚本。

## 目录约定

| 路径 | 用途 | 状态 |
| --- | --- | --- |
| `init/00_create_database.sql` | 创建数据库与应用账号（系统级，不含业务表） | 已提供 |
| `init/` 下的其它脚本 | 后续系统级初始化脚本 | 预留 |
| 业务表结构 | **不在本目录**，由 Alembic 迁移统一管理（`backend/alembic/versions/`） | 已有 M1 草案迁移，待正式设计确认 |

## 为什么业务表结构不放在 sql/

项目采用 Alembic 作为唯一的表结构变更入口，避免出现「手工 DDL 与迁移脚本不一致」的问题：

```
# 在 backend 目录下执行
python -m alembic upgrade head        # 应用迁移
python -m alembic revision --autogenerate -m "描述"   # 生成新迁移
python -m alembic downgrade -1        # 回滚一步
```

现有迁移 `573c803013d2_init_schema.py` 是为跑通端到端演示而编写的**原型草案**，
其中科室 / 床位 / 住院证 / 分配等业务实体、状态取值与约束
**尚未经过业务方确认**，正式结构将在设计评审后另行定稿并生成新的迁移。
