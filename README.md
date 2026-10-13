# 医院床位智能分配与住院入院预办理原型系统

面向医院住院处的**模块化单体**原型系统：从开具住院证、预入院登记（模拟预交金），
到智能床位推荐与床位分配（预占用 / 入住 / 出院 / 释放）的全流程演示。

> ⚠️ **数据安全声明**
> 本项目**仅使用虚构患者数据**，不包含任何真实医疗数据；
> **不接入真实支付**（预交金为模拟记账）、**不使用付费 AI 服务**，
> 所有评分算法均为本地确定性计算。

---

## 一、技术栈

| 层次 | 选型 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite |
| 后端 | FastAPI + SQLAlchemy 2.0 + Alembic |
| 数据库 | MySQL 8 |
| 测试 | pytest（含真实 MySQL 并发与权限用例） |
| 部署 | Docker Compose |
| 架构 | 模块化单体（不引入微服务） |

## 二、目录结构

```
Attention is all you need/
├── backend/                    后端（FastAPI）
│   ├── app/
│   │   ├── api/v1/             路由层（认证、基础数据、住院证、推荐、分配、看板、审计）
│   │   ├── core/               配置、JWT 与口令散列、统一错误、脱敏
│   │   ├── db/                 引擎与会话
│   │   ├── models/             SQLAlchemy 模型与状态枚举
│   │   ├── schemas/            Pydantic 请求/响应模型
│   │   ├── services/           推荐算法、分配事务、审计、序列化、硬约束策略
│   │   └── main.py             应用入口
│   ├── alembic/                数据库迁移
│   ├── tests/                  pytest 测试（44 项）
│   ├── seed.py                 演示数据初始化
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   前端（Vue 3 + TS + Vite）
│   ├── src/{api,layouts,router,views,styles}/
│   ├── package.json
│   ├── nginx.conf
│   └── Dockerfile
├── docs/                       架构、E-R 图、业务流程图、算法说明、隔离床策略
├── sql/                        数据库层脚本（仅建库建号，业务表由 Alembic 管理）
├── docker-compose.yml
├── .env.example
└── README.md
```

## 三、快速开始（Windows）

### 1. 数据库

本项目默认使用**独立的 MySQL 实例**（数据目录在项目内、端口 `3307`），
不会影响你机器上已有的 3306 实例。

```powershell
# 首次初始化数据目录（只需执行一次）
& "C:\mysql-8.0.32-winx64\bin\mysqld.exe" --no-defaults --initialize-insecure `
  --basedir="C:\mysql-8.0.32-winx64" --datadir="E:\Attention is all you need\.mysql\data"

# 启动实例（保持窗口开启；也可做成 Windows 服务）
& "C:\mysql-8.0.32-winx64\bin\mysqld.exe" --no-defaults `
  --basedir="C:\mysql-8.0.32-winx64" `
  --datadir="E:\Attention is all you need\.mysql\data" `
  --port=3307 --bind-address=127.0.0.1 `
  --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci `
  --max-connections=200 --default-time-zone=+08:00 --console

# 创建数据库与应用账号（新开一个终端）
& "C:\mysql-8.0.32-winx64\bin\mysql.exe" -h 127.0.0.1 -P 3307 -u root --skip-password `
  -e "source E:/Attention is all you need/sql/init/00_create_database.sql"
```

已有 MySQL 的用户也可以直接用现成实例，只要改 `.env` 里的 `DATABASE_URL`。

### 2. 后端

```powershell
cd "E:\Attention is all you need\backend"

# 安装依赖
python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ `
  --trusted-host mirrors.aliyun.com -r requirements.txt

# 配置环境变量
Copy-Item .env.example .env     # 如已存在可跳过

# 建表（Alembic 迁移）
python -m alembic upgrade head

# 写入演示数据
python seed.py

# 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

* 接口文档：<http://127.0.0.1:8000/docs>
* 健康检查：<http://127.0.0.1:8000/health>

### 3. 前端

```powershell
cd "E:\Attention is all you need\frontend"
npm install
npm run dev
```

* 管理后台首页：<http://127.0.0.1:5173/>
* 系统状态页：<http://127.0.0.1:5173/system-status>（调用后端 `/health` 与 `/api/v1/system/info` 验证连通性）
* 接口文档：<http://127.0.0.1:5173/docs>（经代理直达后端 Swagger）

开发服务器已在 `vite.config.ts` 中把 `/api`、`/health`、`/docs`、`/redoc`、`/openapi.json`
代理到 `127.0.0.1:8000`，无需额外处理跨域。

### 4. 一键启动（Docker Compose，可选）

```powershell
cd "E:\Attention is all you need"
docker compose up -d --build
docker compose exec backend python seed.py     # 写入演示数据
```

* 前端：<http://localhost:8080>
* 后端：<http://localhost:8000/docs>

> 本机当前未安装 Docker，故 Compose 路径**未实际验证**，仅提供编排文件（见「未完成项」）。

## 四、演示账号

| 账号 | 口令 | 角色 | 可做什么 |
| --- | --- | --- | --- |
| `admin` | `admin123` | 系统管理员 | 全部权限；查看患者明文、查看审计日志；基础数据维护 |
| `doctor01` | `doctor123` | 医生（张明 / 心内科） | 开具住院证、预入院登记、查看推荐 |
| `doctor02` | `doctor123` | 医生（李慧 / 呼吸科） | 同上 |
| `nurse01` | `nurse123` | 护士（王芳） | 预入院登记、床位推荐、预占用 / 入住 / 出院 / 释放 |
| `nurse02` | `nurse123` | 护士（赵强） | 同上 |
| `viewer01` | `viewer123` | 只读用户 | 仅可登录与查看列表/看板 |

## 五、演示操作流程

用 Swagger（<http://127.0.0.1:8000/docs>）或任意 HTTP 客户端按以下顺序走一遍主闭环：

1. **登录**：`POST /api/v1/auth/login`，body `{"username":"admin","password":"admin123"}`，
   拿到 `access_token` 后点 Swagger 右上角 **Authorize** 填入。
2. **看待板**：`GET /api/v1/dashboard/summary`
   → 总床位 44、空床 37、预占用 2、已入住 3、待入院 9、隔离床 9。
3. **看待入院队列**：`GET /api/v1/preadmissions?pending_only=true`
4. **看推荐**：`GET /api/v1/admission-requests/{id}/bed-recommendations`
   → 观察 `score_items` 的五项评分明细与中文理由；
   对同一个患者换成不同 `priority`（危重/轻症）再请求一次，可以看到**排序发生变化**。
5. **预占用**：`POST /api/v1/allocations`
   * 采纳推荐：`{"admission_request_id": 12, "confirm_top_recommendation": true}`
   * 人工选择：`{"admission_request_id": 12, "bed_id": 3}`
     （传跨科室 / 性别冲突的床位会返回 `422 HARD_CONSTRAINT_VIOLATION` 并列出违反项）
6. **入住 → 出院 → 释放**：
   `POST /allocations/{id}/admit` → `POST /allocations/{id}/discharge` → `POST /beds/{bed_id}/release`
   每一步都可用 `GET /beds/{bed_id}/status-logs` 看到状态流水。
7. **越权验证**：用 `viewer01` 的令牌调 `POST /api/v1/admission-requests`
   → `403 PERMISSION_DENIED`；再用 `admin` 调 `GET /api/v1/audit-logs?action=PERMISSION_DENIED`
   → 能看到 `viewer01 / FAILURE` 的审计记录。

前端管理后台（`npm run dev`）当前提供项目首页与系统状态页；
业务页面（看板、床位列表、住院证、推荐结果、分配记录）已具备完整后端接口，
前端页面在后续迭代中补充。

**浏览器验收项已通过**：用无头 Chrome 实际打开
<http://127.0.0.1:5173/> 与 <http://127.0.0.1:5173/system-status>，
页面正常渲染，系统状态页显示「后端服务：连通」并回显后端服务信息，控制台无报错。
截图见 `docs/screenshots/`。

## 六、测试

```powershell
cd "E:\Attention is all you need\backend"
python -m pytest -q
```

**实际结果（2026-10-13，真实 MySQL 8.0.32 @ 127.0.0.1:3307 的 `hospital_test` 库）：**

```
44 passed, 1 warning in 73.00s
```

覆盖范围：

| 文件 | 用例 | 覆盖点 |
| --- | --- | --- |
| `tests/test_smoke.py` | 7 | M0 基础设施：健康检查、OpenAPI、迁移版本、统一错误响应 |
| `tests/test_recommendation.py` | 9 | 普通患者推荐、隔离要求不匹配（双向）、性别冲突、无空床、高优先级适配、优先级非线性验证 |
| `tests/test_allocation_flow.py` | 13 | 人工调整、推荐确认、科室冲突、隔离不匹配、性别冲突、4 类非法状态流转、完整出入院闭环、取消回滚 |
| `tests/test_concurrency.py` | 3 | **两个线程并发抢同一床位**（恰好一成功一失败）、唯一索引兜底、API 层冲突返回 |
| `tests/test_auth_audit.py` | 12 | 登录成功/失败留痕、缺失/非法令牌、越权 403 与审计、脱敏与明文权限、关键操作审计、看板 |

测试库通过 Alembic `upgrade head` 从零建表，因此**每次跑测试都在验证迁移脚本本身**。
并发用例在**真实 MySQL**上执行，不使用 SQLite 的锁行为替代。

## 七、文档

| 文档 | 内容 |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | 架构、分层、技术决策 |
| [docs/er-diagram.md](docs/er-diagram.md) | E-R 图（Mermaid）、索引与状态约束 |
| [docs/business-flow.md](docs/business-flow.md) | 业务流程图、时序图、状态机、权限矩阵 |
| [docs/recommendation-algorithm.md](docs/recommendation-algorithm.md) | 推荐算法：硬约束 + 可解释软约束评分 |
| [docs/isolation-bed-policy.md](docs/isolation-bed-policy.md) | 隔离床使用策略（显式文档化） |
| [docs/m0-checklist.md](docs/m0-checklist.md) | M0 交付项与验收结果 |

## 八、接口一览

| 分组 | 主要端点 |
| --- | --- |
| 系统 | `GET /system/info`、`GET /system/health`（另有无前缀的 `/health`） |
| 认证 | `POST /auth/login`、`GET /auth/me`、`POST /auth/logout` |
| 基础数据 | `/departments`、`/wards`、`/beds`、`/patients`、`/doctors` |
| 住院证 | `POST/GET /admission-requests`、`/{id}/issue`、`/{id}/cancel`、`/{id}/preadmission` |
| 待入院队列 | `GET /preadmissions` |
| 智能推荐 | `GET /admission-requests/{id}/bed-recommendations` |
| 床位分配 | `POST /allocations`、`/{id}/admit`、`/{id}/discharge`、`/{id}/cancel`、`POST /beds/{id}/release`、`GET /beds/{id}/status-logs` |
| 看板 | `GET /dashboard/summary` |
| 审计 | `GET /audit-logs`（仅管理员） |

所有错误统一为：

```json
{ "code": "BED_NOT_AVAILABLE", "message": "床位 C-101-01 当前状态为「已入住」，已被占用",
  "detail": { "bed_id": 1, "status": "OCCUPIED" }, "request_id": "a05a82a314d5478d" }
```

## 九、未完成项与下一阶段建议

**未完成 / 未验证**

1. **Docker Compose 未实际验证**：本机未安装 Docker，`docker-compose.yml`、
   `backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf` 均未执行过。
2. **前端业务页面未实现**：目前只有首页与系统状态页，
   看板 / 床位列表 / 住院证 / 推荐 / 分配记录等页面待补充（后端接口已就绪）。
3. **业务表结构与算法参数为原型草案**：E-R 图、状态机、评分权重尚未经业务方确认。
4. 未接入真实 HIS / 支付 / 大模型 / OR-Tools —— 按需求刻意不做。
5. 未做压测、未做细粒度性能优化（单科室数十张床位下无需优化）。

**下一阶段建议（按优先级）**

1. 确认正式业务表结构、状态机取值与推荐权重，据此生成正式 Alembic 迁移。
2. 补齐前端业务页面（看板 → 待入院队列 → 推荐结果 → 分配记录 → 审计）。
3. 在装有 Docker 的环境验证 Compose 一键启动。
4. 引入推荐结果的「人工反馈」记录，为后续权重调优积累数据。
5. 补充操作审计的可视化检索页（当前仅 API）。
