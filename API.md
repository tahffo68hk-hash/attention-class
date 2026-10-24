# API 接口表

> 本文件由 `scripts/gen_api_md.py` 从 `backend/app/api/v1/*.py` 源码解析生成，与运行时 `/openapi.json` 一致；改动接口后请重新生成。

* 基础地址：`http://127.0.0.1:8000`，统一前缀 `/api/v1`
* 在线文档：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`
* 端点总数：**51**（`/api/v1` 下），另有 `GET /`、`GET /health` 两个无前缀端点
* 运行时 OpenAPI 统计为 **44 条路径 / 53 个操作**（同一路径可能同时有 GET 与 POST）

## 鉴权方式

```http
POST /api/v1/auth/login        # {username, password} -> {access_token, user}
Authorization: Bearer <access_token>   # 之后所有请求带上
```

角色共四种：`admin` 管理员 / `doctor` 医生 / `nurse` 护士 / `viewer01` 只读。越权访问统一返回 `403 PERMISSION_DENIED`，并写入审计日志。

## 接口总表

### 床位分配（9）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/allocations` | 分配记录列表（支持筛选） | JWT（任意已登录角色） |
| `GET` | `/api/v1/allocations/{allocation_id}` | 分配记录详情 | JWT（任意已登录角色） |
| `GET` | `/api/v1/beds/{bed_id}/status-logs` | 床位状态流水（每次状态变化都留痕） | JWT（任意已登录角色） |
| `POST` | `/api/v1/allocations` | 预占用床位（采纳推荐或人工选择，护士 / 管理员） | JWT + 管理员、护士 |
| `POST` | `/api/v1/allocations/{allocation_id}/admit` | 办理入住（预占用 -> 已入住） | JWT + 管理员、护士 |
| `POST` | `/api/v1/allocations/{allocation_id}/cancel` | 取消预占用（预占用 -> 已取消，床位回到空闲） | JWT + 管理员、护士 |
| `POST` | `/api/v1/allocations/{allocation_id}/discharge` | 办理出院（已入住 -> 已出院，床位转清洁中） | JWT + 管理员、护士 |
| `POST` | `/api/v1/allocations/{allocation_id}/reassign` | 原子人工换床（旧预占释放 + 新床预占，在同一事务） | JWT + 管理员、护士 |
| `POST` | `/api/v1/beds/{bed_id}/release` | 床位释放（清洁中 -> 空闲） | JWT + 管理员、护士 |

### 住院证 / 预入院（8）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/admission-requests` | 住院证列表 | JWT（任意已登录角色） |
| `GET` | `/api/v1/admission-requests/{request_id}` | 住院证详情 | JWT（任意已登录角色） |
| `GET` | `/api/v1/admission-requests/{request_id}/history` | 住院证状态流转说明（演示辅助） | JWT（任意已登录角色） |
| `GET` | `/api/v1/admission-requests/{request_id}/preadmission` | 查看预入院登记 | JWT（任意已登录角色） |
| `POST` | `/api/v1/admission-requests` | 开具住院证（医生 / 管理员） | JWT + 管理员、医生 |
| `POST` | `/api/v1/admission-requests/{request_id}/cancel` | 取消住院证（医生 / 管理员） | JWT + 管理员、医生 |
| `POST` | `/api/v1/admission-requests/{request_id}/issue` | 开具草稿住院证（医生 / 管理员） | JWT + 管理员、医生 |
| `POST` | `/api/v1/admission-requests/{request_id}/preadmission` | 预入院登记（护士 / 医生 / 管理员） | JWT + 管理员、医生、护士 |

### 三维正式床位管理（5）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/ward-map/managed-beds/archived` | — | JWT + 管理员 |
| `POST` | `/api/v1/ward-map/managed-beds` | — | JWT + 管理员 |
| `POST` | `/api/v1/ward-map/managed-beds/{bed_id}/archive` | — | JWT + 管理员 |
| `POST` | `/api/v1/ward-map/managed-beds/{bed_id}/restore` | — | JWT + 管理员 |
| `PUT` | `/api/v1/ward-map/managed-beds/{bed_id}/pose` | — | JWT + 管理员 |

### 基础数据-床位（5）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/beds` | 床位列表（支持多维筛选） | JWT（任意已登录角色） |
| `GET` | `/api/v1/beds/{bed_id}` | 床位详情 | JWT（任意已登录角色） |
| `POST` | `/api/v1/beds` | 新增床位（仅管理员） | JWT + 管理员 |
| `POST` | `/api/v1/beds/{bed_id}/status` | 手工调整床位状态（仅管理员，受状态机约束） | JWT + 管理员 |
| `PATCH` | `/api/v1/beds/{bed_id}` | 修改床位属性（仅管理员） | JWT + 管理员 |

### 基础数据-患者（3）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/patients` | 患者列表（默认脱敏） | JWT（任意已登录角色） |
| `POST` | `/api/v1/patients` | 新增患者（管理员/护士） | JWT + 管理员、护士 |
| `PATCH` | `/api/v1/patients/{patient_id}` | 修改患者（管理员/护士） | JWT + 管理员、护士 |

### 认证（3）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/auth/me` | 获取当前登录用户 | JWT（任意已登录角色） |
| `POST` | `/api/v1/auth/login` | 登录获取访问令牌 | 公开 |
| `POST` | `/api/v1/auth/logout` | 退出登录（记录审计） | JWT（任意已登录角色） |

### 辅助解释（教学模拟）（3）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/assistant/provider-status` | DeepSeek 配置状态（不回传密钥） | JWT + 管理员、护士 |
| `POST` | `/api/v1/assistant/explain` | 床位说明：默认确定性规则；真实 AI 须显式确认且服务端启用 | JWT + 管理员、护士 |
| `POST` | `/api/v1/assistant/explain-plan` | 多患者方案解释：默认规则版，DeepSeek 须显式授权（无写入） | JWT + 管理员、护士 |

### 基础数据-医生（2）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/doctors` | 医生列表 | JWT（任意已登录角色） |
| `POST` | `/api/v1/doctors` | 新增医生（仅管理员，可选同时创建登录账号） | JWT + 管理员 |

### 基础数据-病房（2）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/wards` | 病房列表（含床位统计） | JWT（任意已登录角色） |
| `POST` | `/api/v1/wards` | 新增病房（仅管理员） | JWT + 管理员 |

### 基础数据-科室（2）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/departments` | 科室列表 | JWT（任意已登录角色） |
| `POST` | `/api/v1/departments` | 新增科室（仅管理员） | JWT + 管理员 |

### 系统（2）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/system/health` | 健康检查 | 公开 |
| `GET` | `/api/v1/system/info` | 服务信息 | 公开 |

### 3D 调度沙盘（只读）（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/ward-map/simulate` | 完全虚构申请的 H1-H4/五维评分 + 贪心/精确流模拟（零写入） | JWT + 管理员、护士 |

### 多患者联合排床（预览）（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/optimization/preview` | 对同一批待入院患者比较贪心与全局优化（无写入） | JWT + 管理员、护士 |

### 安全与审计（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/audit-logs` | 审计日志查询（仅管理员） | JWT + 管理员 |

### 床位态势图（只读）（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/ward-map` | 全院/病区床位态势快照（模拟空间、真实业务状态） | JWT（任意已登录角色） |

### 待入院队列（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/preadmissions` | 待入院队列（五级优先级优先，同级登记顺序） | JWT（任意已登录角色） |

### 智能床位推荐（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/admission-requests/{request_id}/bed-recommendations` | 获取床位推荐（硬约束过滤 + 可解释软约束评分） | JWT（任意已登录角色） |

### 管理看板（1）

| 方法 | 路径 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/dashboard/summary` | 看板汇总：总床位 / 空床 / 预占用 / 已入住 / 待入院人数 | JWT（任意已登录角色） |

## 统一错误格式

```json
{ "code": "BED_NOT_AVAILABLE", "message": "床位 C-101-01 当前状态为「已入住」，已被占用",
  "detail": { "bed_id": 1, "status": "OCCUPIED" }, "request_id": "a05a82a314d5478d" }
```

| 状态码 | 典型 code | 含义 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 参数校验失败 |
| 401 | `UNAUTHENTICATED` | 未带令牌或令牌无效/过期 |
| 403 | `PERMISSION_DENIED` | 角色不足（会写审计） |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `ILLEGAL_STATE_TRANSITION` / `BED_NOT_AVAILABLE` / `REQUEST_ALREADY_ALLOCATED` | 状态机或并发冲突 |
| 422 | `HARD_CONSTRAINT_VIOLATION` | 违反硬约束（科室 / 性别 / 隔离） |
