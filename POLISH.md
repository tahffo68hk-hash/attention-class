# POLISH.md —— 把它整理成能打开讲的作品

分支：`polish-portfolio`（**未推送**，全部改动仅本地）
整理时间：2026-10
起点提交：`4b619fa`

---

## 一、总览

| # | 任务 | 状态 | 结果 |
| --- | --- | --- | --- |
| 1 | 跑通前后端 + 数据库主流程 | ✅ | 登录 → 床位 → 推荐 → 预占用 → 入住 → 出院 → 释放 全程 200/201；越权 403 + 审计落库 |
| 2 | 接口文档 | ✅ | `/docs` 可打开（44 路径 / 53 操作）；新增 `API.md`（51 端点，源码生成） |
| 3 | `.env.example` | ✅ | 根目录 + `backend/` 两份，覆盖 `config.py` 全部 22 个变量，仅占位符 |
| 4 | 容器化 | ⚠️ 部分 | 补齐 Dockerfile / compose / entrypoint / `.dockerignore`，静态校验通过；**未能实跑**（沙箱禁用 WSL，Docker daemon 起不来） |
| 5 | 全量 pytest | ✅ | `87 passed` + `75 passed` = **162 项全通过，0 失败** |
| 6 | README 重写 | ✅ | 含"规则评分非 AI"说明、Mermaid 架构图、一键启动、测试、截图；本机路径与夸大表述已清除 |
| 7 | 截图 6 张 | ✅ | `demo-screenshots/01~06`，脚本可复跑，无真实凭据、无本机路径 |

---

## 二、逐步做了什么

### 1. 跑通主流程

启动顺序：MySQL 8.0.32（隔离实例 `127.0.0.1:3307`）→ `uvicorn` :8000 → `vite` :5173。

用真实 HTTP 请求验证的闭环（不是"看代码觉得没问题"）：

```
POST /auth/login                    200  role=ADMIN
GET  /dashboard/summary             200  总床位 44 / 空床 37 / 预占用 2 / 已入住 3 / 待入院 9
GET  /beds?page=1&page_size=3       200  total=44
GET  /preadmissions?pending_only=1  200  9 条
GET  /admission-requests/7/bed-recommendations  200  4 张候选，top C-102-04 score=79.24
POST /allocations                   201  id=24 status=RESERVED
POST /allocations/24/admit          200  ADMITTED
POST /allocations/24/discharge      200  DISCHARGED
POST /beds/8/release                200  AVAILABLE（清洁 → 空闲）
GET  /beds/8/status-logs            200  4 条状态流水
POST /admission-requests (viewer01) 403  PERMISSION_DENIED
GET  /audit-logs (admin)            200  能看到上一条 viewer01/FAILURE
```

看板数字与 README 里写的 44 / 37 / 2 / 3 / 9 / 9 完全一致，说明演示数据没被跑偏。

### 2. 接口文档

* `GET /docs` 返回 200，Swagger 正常渲染（见 `demo-screenshots/05-openapi-docs.png`）。
* 新增 `API.md`：由 `scripts/gen_api_md.py` 解析 `backend/app/api/v1/*.py` 的 AST 生成，
  含方法 / 完整路径 / 用途 / 鉴权（角色）。**不手写**，避免以后接口变了表还是旧的；
  支持 `--check` 做一致性校验。

### 3. 环境变量

`backend/.env.example` 从 19 行扩到覆盖 `app/core/config.py` 全部字段：应用元信息、
数据库（含连接池）、JWT、脱敏开关、CORS、P2/P4 外部模型开关与费率。全部为占位值。

根 `.env.example` 改为只服务 compose 插值（`MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` /
`MYSQL_DATABASE` / `SECRET_KEY` / `AUTO_SEED`），并注明本机直跑应改用 `backend/.env`。

### 4. 容器化

改动：

* `backend/Dockerfile`：pip 镜像源改为 `--build-arg` 可覆盖；CMD 交给 entrypoint 脚本。
* `backend/docker-entrypoint.sh`（新增）：`alembic upgrade head` → **空库才** `seed.main()`
  → `uvicorn`。这样 `docker compose up` 一条命令就能得到可点开就用的演示环境，
  又不会每次 `restart` 都清空数据。
* `frontend/Dockerfile`：`npm install` → `npm ci`（lock 不同步时自动回落 install），
  只 copy 依赖清单以命中缓存。
* `docker-compose.yml`：补 backend healthcheck、frontend 依赖 `service_healthy`、
  `TEST_DATABASE_URL` 指向独立的 `hospital_test`、挂载 `docker/mysql/init`。
* `docker/mysql/init/01_create_test_database.sql`（新增）：首次初始化时建 `hospital_test` 并授权。
* 两份 `.dockerignore` 补齐 `.env*` / 缓存 / 虚拟环境。

**验证到什么程度**：`docker compose config` 通过（3 个服务、插值正常）；entrypoint 里的
seed 判定逻辑用真实 Python 在测试库上跑了两个分支（有数据跳过 / 空库写入），均 rc=0。
**没有验证**：镜像构建与容器间网络（原因见第四节）。

### 5. 测试

```
cd backend && python -m pytest -q tests tests_ward_map
================== 87 passed, 1 warning in 59.60s ===================

python -m pytest -q tests_m1_local tests_p1p2 tests_p15 tests_p25
================== 75 passed, 1 warning in 14.66s ===================
```

唯一的 warning 是 `StarletteDeprecationWarning: Using httpx with starlette.testclient`，
来自第三方库，不影响结论，未处理。

### 6. README 与截图

README 重写，删掉了所有 `E:\...`、`C:\...` 本机路径、`PowerShell 双击 .cmd` 的本机脚本说明，
把"未验证的 Docker 路径"从"可选方案"降级为"已知限制"里如实说明。

截图脚本：
* `scripts/demo_screenshots.mjs` —— 登录页 / 床位列表 / 推荐+预占用 / 审计 / Swagger 五张。
* `scripts/pytest_shot.mjs` —— 真实执行 pytest，把 stdout 渲染成终端窗口截一张（06）。

---

## 三、修过的问题（问题 → 原因 → 修法）

### P1　演示库版本落后，接口一调就 500

* **现象**：`GET /beds` 等接口连演示库必然报错。库停在 `9bca1026e001`。
* **原因**：代码已加 `bed_scene_slots` 表与 `beds.retired_at` 列（修订 `20261015ed02`），
  演示库没跟着迁移；SQLAlchemy 生成的 SELECT 带 `retired_at`，MySQL 报未知列。
* **修法**：先做逻辑备份（13 张表全量，249 KB，落 `.workbuddy/backup/`，
  已被 `.gitignore` 排除），再 `alembic upgrade head`。迁移后 6 个用户 / 44 张床 /
  23 条分配 / 340 条审计一条不少。

### P2　用 mysqldump 备份直接失败

* **现象**：`mysqldump: Couldn't execute 'FLUSH TABLES': Access denied`。
* **原因**：应用账号 `hospital_app` 没有 `RELOAD/FLUSH_TABLES` 权限，mysqldump 的
  `--single-transaction` 仍需要 FLUSH TABLES。
* **修法**：改用 Python 逻辑备份（`SHOW CREATE TABLE` + `INSERT`），不依赖额外权限。

### P3　回灌备份时中文乱码（我自己踩的坑，记下来）

* **现象**：`mysql < backup.sql` 报 `ERROR 1366 Incorrect string value: '\x80\xE7\x9B\x91...' for column 'diagnosis'`，
  且因为脚本前半段已 DROP 表，库被删了一半。
* **原因**：mysql 客户端默认按 latin1 读入 SQL 文件，备份文件是 UTF-8。
* **修法**：放弃回灌，改用项目自带的正规路径重建 —— `DROP 全部表 → alembic upgrade head →
  python seed.py`，一次干净复原（44 床 / 37 空 / 9 待入院）。
  **教训**：以后回灌必须带 `--default-character-set=utf8mb4`；能用官方 seed 就别手工回灌。

### P4　待入院列表里混入「已占用」的住院证，点采纳必报 409

* **现象**：推荐页左侧选第一张住院证 → 点"采纳推荐第一名" → 顶部红条
  `[REQUEST_ALREADY_ALLOCATED] 同一住院证已有活动分配`。
* **原因**：列表只按 `status=PRE_ADMITTED` 过滤，而住院证入住前一直是这个状态；
  前端没有结合分配记录判断"是否已有活动分配"。后端唯一约束是对的（409 是正确兜底），
  错在前端让用户点了必然失败的按钮。
* **修法**：`RecommendationView.vue` 的 `loadCandidates()` 并行拉 `/allocations`，
  过滤掉 `RESERVED/ADMITTED` 的住院证，并处理"选中项被过滤掉"的情况；空态文案同步说明。
  只改前端展示层，**不碰后端事务与状态机**，后端 409 仍是最终防线。改完 `vue-tsc` 0 错。

### P5　采纳成功后的提示立刻消失，用户以为没成功

* **现象**：分配其实成功了（库里有记录），但页面看不到任何"已预占用"提示。
* **原因**：`adopt()` 先写 `actionMessage`，随后 `loadRecommendations()` 开头
  `actionMessage.value = ''` 把它清掉了。
* **修法**：提示文案改为**在刷新之后**赋值；清理动作只留在用户主动切换住院证时。
  修完 03 截图里能看到 `已预占用床位 O-301-04（分配 #7，状态：预占用）`。

### P6　compose 的测试库指向演示库（会毁数据）

* **现象**：`TEST_DATABASE_URL` 和 `DATABASE_URL` 都指向 `hospital`。
* **原因**：编排时图省事复制了一行。
* **修法**：新增 `docker/mysql/init/01_create_test_database.sql` 建 `hospital_test` 并授权，
  compose 里 `TEST_DATABASE_URL` 指向它。`conftest.py` 的 fail-closed 守卫（库名必须
  `*_test`）仍在，双保险。

### P7　后端镜像会把真实 `.env` 打进镜像层

* **现象**：`backend/Dockerfile` 是 `COPY . .`，而本机 `backend/.env` 里有真实口令与 SECRET_KEY。
* **原因**：`.dockerignore` 只写了 `.env`，漏了 `.env.local` 之类的变体，也没有说明性注释。
* **修法**：`backend/.dockerignore` 补 `.env*` + `!.env.example`，排除缓存/覆盖率/虚拟环境；
  `frontend/.dockerignore` 同样补齐（`node_modules` 本来就排了，否则 Windows 依赖会覆盖
  Linux 依赖，`rollup` 直接报错）。

### P8　截图里带出了本机绝对路径

* **现象**：06 截图里出现 `C:\Users\...\python.exe`、`rootdir: E:\...\backend`。
* **原因**：直接截 pytest 原始 stdout。
* **修法**：`pytest_shot.mjs` 增加清洗：去掉第三方 warning 段（全是 site-packages 路径），
  绝对路径统一替换为 `<repo>` / `<path>`，命令行只显示 `python -m pytest ...`。
  截图内容仍是本次真实执行输出。

### P9　README 与事实不符

* **现象**：README 写"`tests/` 44 项""51 passed""前端业务页面未实现（只有首页与系统状态页）"，
  但实际已有 12 个页面、87 项测试。
* **原因**：文档停在早期里程碑，后续开发没回填。
* **修法**：README 全量重写，数字全部以本次实测为准（162 项测试、51 端点、12 页面）。

---

## 四、仍有风险 / 未完成

1. **Docker 端到端未实跑（最高优先级）**
   沙箱把 `wsl.exe` 列入程序黑名单，Docker Desktop 的 Linux 引擎起不来
   （`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`）。
   已完成：`docker compose config` 静态校验、entrypoint seed 分支单测、`.dockerignore` 审计。
   未完成：`docker compose build` / 容器间 `mysql:3306` 连通性 / nginx 反代实际链路。
   → 换个有 Docker 的机器，跑一次 `docker compose up --build` 即可关闭此项。

2. **截图 06 是"渲染的终端窗口"**：内容来自真实 pytest stdout，但外观由 HTML/CSS 绘制，
   不是真实终端截图。面试若要"纯原生截图"，在终端里跑一次再截即可。

3. **评分权重与状态机仍是原型草案**：0.32/0.28/0.18/0.12/0.10 没有业务方确认，
   面试时应说明"权重可配置，需要业务定标"，不要讲成临床结论。

4. **隔离床策略是不降级的硬规则**：真实医院会有加床、跨科借床等弹性处理，当前实现
   无床位时直接返回原因。这是刻意的简化，不是遗漏。

5. **演示库已被迁移到 head**：本地 `.workbuddy/backup/hospital_before_polish.sql` 是旧 schema
   备份（未提交）。若要回到整理前状态，需 drop 库 + 回灌该 SQL（记得
   `--default-character-set=utf8mb4`）+ 再 `alembic downgrade`/手工删列。

6. **未做的性能工作**：没有压测、没有分页游标优化。44 张床的规模下不需要，
   但被问"怎么扛 5000 床"要能答出：索引 + 候选集预过滤 + 推荐结果缓存 + 只读副本。

7. **`docker-entrypoint.sh` 的 `AUTO_SEED`**：只判断 `users` 表是否为空。若有人手工清空
   业务表但保留用户，不会自动补数据（这是有意的保守行为）。

---

## 五、改动文件清单

新增：

```
API.md                                       接口总表（源码生成）
POLISH.md                                    本文件
docker-compose.yml                           重写（healthcheck / 测试库 / init 挂载）
docker/mysql/init/01_create_test_database.sql
backend/docker-entrypoint.sh
scripts/gen_api_md.py                        API.md 生成器（支持 --check）
scripts/demo_screenshots.mjs                 5 张界面截图
scripts/pytest_shot.mjs                      测试通过截图
demo-screenshots/01-login.png
demo-screenshots/02-bed-list.png
demo-screenshots/03-allocate.png
demo-screenshots/04-audit-log.png
demo-screenshots/05-openapi-docs.png
demo-screenshots/06-pytest-pass.png
```

修改：

```
README.md                                    全量重写
.env.example                                 compose 变量 + AUTO_SEED 说明
backend/.env.example                         覆盖 config.py 全部变量
backend/Dockerfile                           build-arg 镜像源 + entrypoint
backend/.dockerignore                        补 .env* / 缓存排除
frontend/Dockerfile                          npm ci + 仅 copy 依赖清单
frontend/.dockerignore                       补 .env*
frontend/src/views/RecommendationView.vue    过滤已分配住院证（P4）+ 成功提示不被覆盖（P5）
```
