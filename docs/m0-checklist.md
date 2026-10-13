# M0 工程初始化 —— 交付项与验收结果

验收时间：2026-10-13 · 环境：Windows 11 · Python 3.13.14 · Node 22.22.2 · MySQL 8.0.32

## 一、交付项

| # | 交付项 | 状态 | 产物 |
| --- | --- | --- | --- |
| 1 | 前端项目初始化 | ✅ | `frontend/`（Vue 3.5 + TypeScript 5.6 + Vite 5.4） |
| 2 | 后端项目初始化 | ✅ | `backend/`（FastAPI + SQLAlchemy 2.0 + Alembic） |
| 3 | 数据库连接配置 | ✅ | 隔离 MySQL 8 实例（端口 3307）+ `backend/.env` + `.env.example` |
| 4 | 环境变量示例 | ✅ | `.env.example`（根目录）、`backend/.env.example`、`frontend/.env.development`、`.env.production` |
| 5 | 项目目录结构 | ✅ | 前后端分离 + `docs/` + `sql/` |
| 6 | `docs/` 目录 | ✅ | 架构、E-R 图、业务流程图、算法说明、隔离床策略 |
| 7 | `sql/` 目录 | ✅ | `sql/init/00_create_database.sql`（仅建库建号）+ `sql/README.md` |
| 8 | 依赖清单 | ✅ | `backend/requirements.txt`、`frontend/package.json`（含 lock） |
| 9 | Docker Compose 与 Dockerfile | ✅ 已编写 / ⚠️ 未运行 | `docker-compose.yml`、`backend/Dockerfile`、`frontend/Dockerfile` |
| 10 | `.gitignore` | ✅ | 根目录 `.gitignore`（含 `.mysql/` 数据目录、`node_modules`、`backend/.env`） |
| 11 | 基础测试 | ✅ | `backend/tests/`（44 项，全部通过） |
| 12 | README（含 Windows 启动命令） | ✅ | `README.md` |
| 13 | Git 仓库与首次提交 | ✅ | 本地 commit（不 push） |

## 二、验收结果

### 1. 后端启动与健康检查

```
GET http://127.0.0.1:8000/health  ->  200 {"status":"ok"}
GET http://127.0.0.1:8000/        ->  200 {"name":"医院床位智能分配与住院入院预办理系统",
                                          "version":"0.1.0","docs":"/docs","api_prefix":"/api/v1"}
GET http://127.0.0.1:8000/openapi.json -> 200（30 条路径）
```

### 2. 前端启动与页面访问

```
GET http://127.0.0.1:5173/        ->  200，HTML 含中文标题「医院床位智能分配与住院入院预办理系统」
GET http://127.0.0.1:5173/health  ->  200 {"status":"ok"}   # 经 Vite 代理调用后端健康接口
```

前端构建（类型检查 + 打包）通过：

```
> vue-tsc --noEmit && vite build
✓ 93 modules transformed.
dist/index.html                    0.41 kB
dist/assets/index-*.css            3.25 kB
dist/assets/index-*.js            94.03 kB
✓ built in 941ms
```

### 3. 数据库迁移

```
python -m alembic upgrade head
INFO [alembic.runtime.migration] Running upgrade  -> 573c803013d2, init schema
```

### 4. 自动化测试

```
44 passed, 1 warning in 73.00s
```

| 文件 | 通过 |
| --- | --- |
| `test_smoke.py`（基础设施） | 7 |
| `test_recommendation.py` | 9 |
| `test_allocation_flow.py` | 13 |
| `test_concurrency.py`（真实 MySQL 并发） | 3 |
| `test_auth_audit.py` | 12 |

### 5. 数据链路（后端 → MySQL）

```
总床位 44 | 空床 37 | 预占用 2 | 已入住 3 | 清洁中 1 | 维护中 1 | 待入院 9 | 隔离床 9（可用 8）
科室 5 个 / 病房 12 间 / 患者 20 人 / 医生 5 人 / 用户 6 个 / 住院证 16 张
```

## 三、过程中修复的真实缺陷（均有验证）

| # | 问题 | 现象 | 修复 |
| --- | --- | --- | --- |
| 1 | 口令散列拼接分隔符写错（`"${}".format(...)`） | 所有账号**无法登录**（401） | 改为 `"$".join([...])`，并补充验证脚本 |
| 2 | 枚举用 `(str, enum.Enum)`，`str()` 返回限定名 | 看板统计**全为 0**（`BedStatus.AVAILABLE` ≠ `"AVAILABLE"`） | 全部改用 `enum.StrEnum` |
| 3 | `auth` 路由未挂载到 `api_router` | 登录接口 **404** | 补充 `include_router(auth.router)` |
| 4 | 预入院请求体重复要求 `admission_request_id` | 走 URL 路径调用时 **422** | 请求体中该字段改为可选 |
| 5 | 分配时先判硬约束再判状态 | 抢占已占用床位返回 422 而非 409 | 调整为先判状态（409）再判其它硬约束（422） |

## 四、环境阻塞与说明

| 项 | 说明 |
| --- | --- |
| **Docker 不可用** | 本机未安装 Docker，`docker compose` 路径**未实测**；编排文件已按规范编写（含 healthcheck 与依赖顺序），需在有 Docker 的环境验证 |
| **本机 shell 缺 coreutils** | 本机 Git Bash 无 `ls/cat/mkdir/grep` 等，所有命令改用 Python 与专用工具执行；不影响项目本身 |
| **pip 默认源不可用** | 清华源返回 403，改用阿里云镜像；Dockerfile 中已固定阿里云源 |
| **数据库隔离** | 为不改动机器上既有的 MySQL 3306 实例，本项目使用独立 datadir + 3307 端口 |

## 五、明确的边界（按需求刻意不做）

* 未接入真实 HIS、真实支付、付费 AI 服务；
* 未引入大模型、OR-Tools 或复杂全局优化；
* 未编写/修改任何**业务数据表结构**的正式定稿
  —— 现有迁移为跑通端到端演示的原型草案，正式结构待业务方确认；
* 未实现前端业务页面（后端接口已就绪）。
