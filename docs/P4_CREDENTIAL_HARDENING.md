# P4 凭据风险关闭与真实 Pilot 前置检查

```
CREDENTIAL_HARDENING = DONE（跟踪文件已无可用凭据；本机隔离实例凭据已轮换并验证）
PROVIDER_REQUEST_ID  = DONE（已解析并在响应/审计中记录，含针对性测试）
PILOT_CONCURRENCY    = FIXED（发现并修复真实竞态：上限与预算校验可被并发绕过）
REAL_DEEPSEEK_PILOT  = 仍为 BLOCKED（本机未配置 DEEPSEEK_API_KEY；**本次未发起任何付费调用**）
```

- **起始基线（实测 `git rev-parse HEAD`）**：`26b602d`
- **公开边界**：`origin/main` = `f318058`（远端 `git ls-remote` 复核一致）
- **本地领先远端**：6 个提交（`b3c2a97`…`26b602d`），**本次仍不 push**
- **真实付费 API 调用**：**0 次**（未新增授权、未配置密钥）
- **业务数据**：未删除、未新增（见 §6 关于演示库被操作者正常使用的说明）

---

## 1. 凭据是否曾公开暴露：判定与证据

判定方法：把凭据取值当字符串，在**已推送历史**（`git log origin/main -S<value>`）与
**公开树顶端**（`git grep -e <value> origin/main`）中搜索。搜索只在进程内进行，
报告与证据文件**只记录 SHA256 指纹与长度，不记录明文**。

结论：**是的，曾有 6 个取值随公开历史暴露**，全部由本次之前的提交引入，且到
`origin/main` 顶端仍然存在。

### 1.1 可访问持久资产的凭据（高风险，必须处理）

| # | 凭据 | 指纹 | 长度 | 引入提交 | 公开 |
|---|---|---|---|---|---|
| 1 | 应用 `SECRET_KEY`（仓库默认值） | `0fc6b32a6011` | 38 | `27110a9`(M0) | 是 |
| 2 | `hospital_app` 数据库口令 | `1c954a13edbe` | 17 | `27110a9`(M0) | 是 |
| 3 | MySQL `root` 口令 | `d41ca9b3ff93` | 8 | `27110a9`(M0) | 是 |

**有效性实测（不是"看起来像弱口令"，而是确实在用）**

- 用**公开历史里的 root 口令**连接 `127.0.0.1:3307` → **成功**（`root@localhost`）；
- 用**公开历史里的 app 口令**连接 → **成功**；
- `settings.SECRET_KEY` 与公开值指纹一致 → 当时签发的 JWT 即由公开密钥签名
  （实测：用公开值伪造 `role=ADMIN` 的令牌，应用**接受**）。

> 风险定级：1 号最严重 —— JWT 签名密钥公开 ⇒ 任何能访问该服务的人可自行签发
> 管理员令牌。2/3 号次之 —— 实例仅绑定 `127.0.0.1`、且为课程隔离实例，
> 但口令已公开，属"已知口令"状态。

### 1.2 仅作用于一次性 CI 容器的凭据（低风险，未轮换）

`.github/workflows/ci.yml` 中另有 3 个明文取值：

| 凭据 | 指纹 | 长度 | 引入提交 |
|---|---|---|---|
| CI `SECRET_KEY` | `e9c1a8da9ae2` | 55 | `7d6789e` |
| CI `MYSQL_ROOT_PASSWORD` | `5d9367c45543` | 15 | `7d6789e` |
| CI `MYSQL_PASSWORD` | `610781d5fc98` | 13 | `7d6789e` |

它们只用于 GitHub Actions job 内**临时启动、job 结束即销毁**的 mysql 服务容器，
不连接任何持久资产、不给外部系统授权，**不构成可被利用的秘密**。
处理方式：**加注释显式声明其作用域**（不改取值 —— 改一个"写在公开文件里的值"
没有任何安全收益），并在 §7 给出改走 Actions Secrets 的方案（需你确认后执行）。

### 1.3 明确**未**发现

- 未发现 DeepSeek / OpenAI 等外部服务的 API Key 入库（两处 `*_API_KEY` 均为空）。
- 未发现生产环境凭据；全部为本地隔离实例与课程演示用途。

证据：`docs/evidence/credential_hardening/exposure_audit_before.txt`

---

## 2. 配置迁移结果（不含秘密值）

原则：**受版本控制的文件里只允许出现不可用占位符**；真实取值只存在于被
`.gitignore` 排除的本机 `.env`。

| 文件 | 变更 |
|---|---|
| `backend/app/core/config.py` | `SECRET_KEY` / `DATABASE_URL` / `TEST_DATABASE_URL` 默认值改为占位符（`CHANGE_ME_*`）；新增两个 `field_validator`，**一旦占位符生效即拒绝启动**并给出可操作提示（fail-fast，避免"默认弱口令"静默生效） |
| `docker-compose.yml` | 所有口令改为 `${MYSQL_ROOT_PASSWORD:?}` / `${MYSQL_PASSWORD:?}` / `${SECRET_KEY:?}` 变量插值；缺失即报错。健康检查改用 `$$MYSQL_ROOT_PASSWORD`，compose 配置里不再出现明文 |
| `sql/init/00_create_database.sql` | 改为**模板**，只含 `__APP_DB_PASSWORD__`；新增 `scripts/render_sql_init.py` 从环境变量/`backend/.env` 渲染后执行（取不到口令即 exit 2，不回落默认值），保留建库建号能力 |
| `.env.example`、`backend/.env.example` | 全部改为 `<YOUR_APP_DB_PASSWORD>` / `<YOUR_SECRET_KEY>` 等占位符，并补充 compose 变量说明 |
| `.gitignore` | 新增 `.env`（不带斜杠 → 覆盖根目录 compose 用 `.env`；**不会**误伤 `.env.example`） |
| `backend/app/schemas/auth.py` | OpenAPI 登录示例由真实演示口令改为 `<your-password>`（`/docs` 不再展示可用口令） |
| `.github/workflows/ci.yml` | 增加作用域说明注释（见 §1.2） |
| `README.md`、`sql/README.md` | 同步新的初始化流程与凭据约定 |

**本地 MySQL 启动能力保留**：应用读取 `backend/.env`（已含真实取值）→ 实测
`settings.DATABASE_URL` 连接成功并查询到 `beds=44` 行、MySQL 8.0.32。

**占位符 fail-fast 实测**：
`SECRET_KEY=CHANGE_ME_SECRET_KEY` → 启动即 `ValidationError`；
连接串含 `CHANGE_ME_DB_PASSWORD` → 同样拒绝启动。

### 2.1 决定性核查（比正则审计更硬）

把公开历史里的每个取值逐个取出，再在工作区搜一遍：
**5 个"持久资产类"取值在受版本控制的文件中命中数 = 0**。

证据：`docs/evidence/credential_hardening/no_leak_verification.txt`、
`docs/evidence/credential_hardening/exposure_audit_after.txt`

---

## 3. 轮换与验证

已执行（本地隔离实例，可安全实施；**不重写远程历史、不 push**）：
`root@localhost`、`hospital_app@%` 两个账号的 MySQL 口令，以及应用 `SECRET_KEY`。

做法要点：
- 旧值从公开历史解析（脚本自身不含明文），写入路径只有 gitignored 的
  `backend/.env`（应用）与根 `.env`（compose 插值）；
- **任何一步失败即回滚**（ALTER 失败、验证不通过都会用旧口令改回去）；
- 全程只输出长度与指纹；脚本实现在本机一次性使用，未入库。

验证结果：

| 检查 | 结果 |
|---|---|
| `root` 旧口令（指纹 `d41ca9b3ff93`）连接 | ✅ 已失效 |
| `hospital_app` 旧口令（指纹 `1c954a13edbe`）连接 | ✅ 已失效 |
| `hospital_app` 新口令（`backend/.env`）连接 | ✅ 可用 |
| `root` 新口令（根 `.env`）连接 | ✅ 可用 |
| **旧公开密钥签发的 JWT** | ✅ **REJECTED (InvalidSignatureError)** |
| 当前密钥签发的 JWT | ✅ ACCEPTED |
| 应用走 `settings.DATABASE_URL` 真实查询 | ✅ `beds=44` / MySQL 8.0.32 |

证据：`docs/evidence/credential_hardening/rotation_verification.txt`

> 轮换是**不可逆**的（旧口令已失效）。旧值仍留在公开历史里，见 §7。

---

## 4. DeepSeek Provider：解析并记录响应 id

**改动**

- `app/services/deepseek_provider.py`：
  - `DeepSeekResult` 新增 `request_id: str | None = None`（**放在末位并带默认值**，
    不破坏既有位置参数构造 —— 已有两处集成测试正是按位置构造的）；
  - 新增白名单收窄函数 `_safe_request_id()`：只接受匹配
    `^[A-Za-z0-9._:\-]{1,128}$` 的字符串，其余（空、含空格/换行、超长、
    非字符串、`Bearer sk-…` 形态）一律丢弃为 `None`；
  - **缺失或不合规不会让整次解释失败**（id 是辅助信息，不是业务必需项）。
    这同时也堵住了"把任意上游文本带进审计/日志"的注入面。
- `app/schemas/assistant.py`：`ExplainOut` / `PlanExplainOut` 新增可选 `request_id`。
- `app/services/assistant_explanation.py`：两条路径都把 `ai.request_id` 透出。
- `app/api/v1/assistant.py`：成功路径的审计明细新增 `provider_request_id`，
  用于与平台账单/用量对账（仍不含任何患者/床位信息）。

**测试**（`backend/tests_p4/test_deepseek_provider.py`，全部零网络 MockTransport）

- 存在合法 id → 正确解析；
- `id` 缺失 → `None` 且解释结果不受影响；
- 参数化 10 种不合规输入（空串/空格/数字/字典/列表/含空格/含换行/`Bearer sk-…`/超长）→ 全部 `None`；
- 把密钥塞进 `id` → 返回对象里**不含**该字符串。

**集成透出**（`backend/tests_p1p2/test_p1p2_integration.py`）：单床与整批两条路径
均断言 `resp.request_id` 等于 mock provider 返回的 id。

OpenAPI 复核：`ExplainOut`(22 字段) / `PlanExplainOut`(19 字段) 均含 `request_id`。

---

## 5. Pilot 执行器并发安全检查

**结论：存在真实缺陷，已最小范围修复。**

### 5.1 缺陷（修复前实测）

`reserve_attempt()` 原文是「读计数 → 校验上限/预算 → 占用额度 → 落盘」四步，
彼此之间**没有任何互斥**。用真实子进程 + 文件栅栏让 12 个实例同时进入临界区：

- **12 个实例中 4 个都判定自己是"第 1 次"**（`OK 1`），即每个都会真的发出一次
  真实付费请求 —— 授权上限 2 次被绕过；
- 而落盘计数只有 **1**（后写覆盖先写），事后审计看不出超发；
- `save_state()` 还共用固定 `.tmp` 文件名，并发时直接 `PermissionError` 崩溃
  （首轮实测：12 个进程里 11 个崩溃）。

### 5.2 修复（`scripts/p4_real_pilot.py`）

1. **跨进程排他锁** `state_lock()`（Windows `msvcrt` 字节锁 / POSIX `fcntl.flock`），
   覆盖整个「读 → 校验 → 占用 → 落盘」序列，并在**锁内重新读取磁盘状态**，
   因此并发实例被串行化：第 3 个及以后一定看到已满的计数。
   - 踩坑：Windows 的字节锁是**强制锁**，锁被占用时连 `os.open(O_RDWR)` 都失败
     （`Errno 13`），因此 `open` 必须与加锁一起放进有界重试循环（超时 → 拒绝执行）。
2. **临时文件名改为每进程唯一**（`pid + uuid8`），并对 `replace` 做有界重试
   （Windows 并发替换目标可能瞬时失败）。
3. **预算校验计入"在途预留"**：余量 = 授权预算 − 已结算花费 − 所有 `IN_FLIGHT`
   预留的最坏情况上界；否则连续/并发两次调用都按同一份余量判断，预算校验形同虚设。

### 5.3 修复后验证

| 场景 | 结果 |
|---|---|
| 16 并发、单次最坏 ¥0.001（上限 2 次） | 成功 **2**、拒绝 14、落盘 `attempts=2`、**0 个异常退出** |
| 8 并发、单次最坏 ¥0.3（预算 ¥0.5） | 成功 **1**、拒绝 7、落盘 `attempts=1` |
| 连续 3 轮 16 并发 | 每轮都是 2 成功 / 14 拒绝，**未突破** |

常驻回归测试：`backend/tests_p4/test_pilot_runner_concurrency.py`（5 项，真实子进程 + 栅栏）。
可复现工具：`scripts/p4_pilot_race_probe.py`。
证据：`docs/evidence/credential_hardening/pilot_concurrency_after.txt`

### 5.4 执行器三个入口回归

`--status` 正常（Pilot ID 仍为持久化的 `P4PILOT-20261014T140727+0800`）；
`--dry-run` 24/24 PASS、真实请求 0；`--execute` 无密钥时 **exit 2** 且未消耗任何额度。

---

## 6. 测试执行情况（只跑受影响面）

| 套件 | 范围 | 结果 |
|---|---|---|
| `tests/`（真实 MySQL 3307） | 凭据轮换 + 配置迁移 + Alembic 重建 + 认证/并发/分配 | **57 passed** |
| `tests_p4` | Provider（含 request id 新增用例）+ **Pilot 并发闸门** | **38 passed** |
| `tests_p1p2` | 联合优化 + 辅助解释（含 request id 透出） | **36 passed** |
| `tests_p25` | API e2e / 破坏性护栏 / 故障注入 | **13 passed** |
| `tests_m1_local` | SQLite 行为回归 | **21 passed** |
| `tests_p15`、`tests_p3` | 矩阵 / P3 闸门回归 | **17 passed** |
| 应用启动 + OpenAPI 冒烟 | `app.main` 导入、37 条路径、schema 含 `request_id`、`/docs` 不再含演示口令 | PASS |

合计 **182 项通过**。未重复运行与本次改动无关的前端构建与浏览器验收。

> **演示库被正常使用中**：会话期间 `hospital` 库出现操作者本人（admin@127.0.0.1）
> 经前端的 `RECOMMEND`(27) / `RESERVE_BED`(8) / `UPDATE`(4) 审计记录
> （`bed_allocations` 15→23、`active` 5→13）。这些写入**不是**本次工具链产生
> （本脚本只读 + 直接调服务层，不写审计），已逐条核对来源。因此
> `--dry-run` 的脱敏载荷会随演示库变化，已在
> `docs/P4_DEEPSEEK_REAL_PILOT.md` §4.2 加注并同步刷新为同一时刻的一致快照。

---

## 7. 剩余阻塞项与建议（需你决策的高风险操作，本次**未执行**）

1. **真实 DeepSeek Pilot 仍为 BLOCKED**：`DEEPSEEK_API_KEY` 未配置。
   解除方式：在 `backend/.env` 填入密钥（仅本机）→ 重启后端 →
   `--execute` → **完事立即把 `DEEPSEEK_EXTERNAL_ENABLED` 改回 `false`**。
2. **公开历史仍留存旧凭据（3 个持久资产类）** —— 这是本轮**唯一**需要你拍板的高风险项。
   现状：口令已在**本机**轮换失效，但那 3 个旧取值仍可被任何人在 GitHub 历史里读到。
   可选方案（**未执行**，请选择其一）：
   - **A. 不改写历史（推荐，零风险）**：既然本机口令已轮换、密钥已换，旧值已无用；
     仅需确认没有**其他**环境（其他机器、部署、同学的环境）仍在复用这些旧值。
   - **B. 改写远程历史**（`git filter-repo` / BFG + `git push --force`）：
     会**重写已公开的提交 SHA**，破坏所有已克隆副本与引用，且 GitHub 上仍可能被
     fork/缓存保留。需你明确授权，且执行前必须先备份并通知协作者。
   - **C. 最省事的缓解**：保持历史不变，但确认仓库无其他敏感物（本项目只有演示数据）。
3. **CI 明文口令改走 Secrets**：把 `ci.yml` 的 3 个值换成
   `${{ secrets.CI_MYSQL_PASSWORD }}` 等 —— 需要你在 GitHub 仓库里先配置 Secrets，
   否则 CI 会红。**未执行**，等你确认。当前这些值已注释声明为一次性容器口令。
4. **演示账号口令（`admin123` 等）仍公开且仍有效** —— 属课程演示账号，且散落在
   `README.md`、`seed.py`、`conftest.py`、前端 `LoginView.vue`、e2e 等约 7 个文件，
   轮换会牵动文档与测试。**未执行**，建议作为独立任务处理（或明确接受其公开）。
5. `deepseek_provider._parse` 现已映射响应 `id`；但**平台账单仍需以控制台为准**，
   本地 `cost_estimate_cny` 只是按显式配置费率做的保守估算。

---

## 8. Git

- **起始 HEAD**：`26b602d`（工作区干净，本地领先 `origin/main` 6 个提交）
- **本次提交**：见下方 `git log`；**本地提交，NO PUSH**
- 未推送原因：本次新增/修改的文件均已确认为占位符或非敏感内容；
  是否推送由你在 §7 决策后决定。
