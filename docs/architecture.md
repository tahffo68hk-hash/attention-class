# 系统架构

## 总体结构

采用**模块化单体**架构：一个后端进程 + 一个前端静态站点 + 一个 MySQL 实例，
不引入微服务、消息队列或分布式组件。

```
┌──────────────────────────┐
│  浏览器（中文管理后台）    │
│  Vue 3 + TypeScript      │
│  Vite dev server :5173   │
└────────────┬─────────────┘
             │ HTTP /api/v1/**（开发经 Vite 代理，生产经 Nginx 反向代理）
┌────────────▼─────────────┐
│  FastAPI 应用 :8000       │
│  ├─ api/v1     路由层     │
│  ├─ services   业务层     │
│  ├─ models     ORM 模型   │
│  ├─ schemas    Pydantic   │
│  └─ core       配置/安全/错误 │
└────────────┬─────────────┘
             │ SQLAlchemy 2.0 + PyMySQL
┌────────────▼─────────────┐
│  MySQL 8 :3307（隔离实例）│
│  迁移由 Alembic 管理      │
└──────────────────────────┘
```

## 后端分层

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 路由层 | `backend/app/api/v1/` | HTTP 入参校验、鉴权依赖、调用业务层、序列化输出 |
| 业务层 | `backend/app/services/` | 推荐算法、分配事务、审计、序列化、硬约束策略 |
| 模型层 | `backend/app/models/` | SQLAlchemy 2.0 声明式模型与状态枚举 |
| 模式层 | `backend/app/schemas/` | Pydantic 请求/响应模型（同时生成 OpenAPI） |
| 核心层 | `backend/app/core/` | 配置、JWT 与口令散列、统一错误、脱敏工具 |
| 数据层 | `backend/app/db/` | 引擎与会话工厂 |

## 前端分层

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 入口 | `frontend/src/main.ts`、`App.vue` | 应用挂载 |
| 路由 | `frontend/src/router/` | 页面路由与标题 |
| 布局 | `frontend/src/layouts/` | 侧边栏 + 内容区骨架 |
| 页面 | `frontend/src/views/` | 首页、系统状态、404 |
| 接口 | `frontend/src/api/` | axios 实例、统一错误封装、系统接口 |

## 关键工程决策

| 决策 | 说明 |
| --- | --- |
| 口令散列用 PBKDF2-HMAC-SHA256 | 标准库实现，避免 bcrypt 二进制轮子在 Windows 上的安装问题；迭代 20 万次 |
| 迁移唯一入口是 Alembic | 不手工改表，保证「代码模型 = 数据库结构」 |
| 并发保护双重保险 | 业务层 `SELECT ... FOR UPDATE` 行锁 + 数据库唯一索引兜底 |
| 统一错误响应 | 所有异常经 `register_exception_handlers` 归一为 `{code, message, detail, request_id}` |
| 默认脱敏 | 姓名/手机号/证件号/地址默认打码，明文需管理员显式请求且写入审计 |
| 本地数据库隔离 | 使用独立 datadir 与 3307 端口，不改动宿主机既有的 3306 实例 |

## 技术栈版本

| 组件 | 版本 |
| --- | --- |
| Python | 3.13 |
| FastAPI | ≥ 0.115 |
| SQLAlchemy | ≥ 2.0.30 |
| Alembic | ≥ 1.13 |
| PyMySQL | ≥ 1.1 |
| Node.js | 22 |
| Vue | 3.5 |
| Vite | 5.4 |
| TypeScript | 5.6 |
| MySQL | 8.0 |
