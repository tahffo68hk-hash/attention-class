# 业务流程

## 主流程

```mermaid
flowchart TD
    A[医生开具住院证] -->|记录患者/科室/优先级/隔离需求| B{是否直接开具}
    B -->|否| A1[草稿 DRAFT]
    A1 -->|开具| A2[已开具 ISSUED]
    B -->|是| A2
    A2 --> C[预入院登记<br/>补充信息 + 模拟预交金]
    C --> D[待入院队列 PRE_ADMITTED]
    D --> E[智能床位推荐]
    E --> F{是否有满足硬约束的床位}
    F -->|否| F1[返回无床原因<br/>科室无空床/隔离床不足/性别冲突]
    F -->|是| G{分配方式}
    G -->|采纳推荐| H1[确认推荐首位]
    G -->|人工选择| H2[指定床位<br/>仍需通过硬约束校验]
    H1 --> I[预占用 RESERVED<br/>行锁 + 唯一索引]
    H2 --> I
    I --> J[办理入住 OCCUPIED]
    J --> K[办理出院 DISCHARGED<br/>床位转 CLEANING]
    K --> L[床位释放 AVAILABLE]
    I -.->|取消| M[取消 CANCELLED<br/>床位回到 AVAILABLE]
```

## 状态流转时序

```mermaid
sequenceDiagram
    autonumber
    participant D as 医生
    participant N as 护士/管理员
    participant API as FastAPI
    participant DB as MySQL

    D->>API: POST /admission-requests（开具住院证）
    API->>DB: INSERT admission_requests（ISSUED）
    N->>API: POST /admission-requests/{id}/preadmission
    API->>DB: INSERT preadmissions + status=PRE_ADMITTED
    N->>API: GET /admission-requests/{id}/bed-recommendations
    API->>DB: SELECT 床位（硬约束过滤）+ 软约束评分
    API-->>N: 排序结果 + 分数明细 + 推荐理由
    N->>API: POST /allocations（bed_id 可空）
    API->>DB: BEGIN; SELECT ... FOR UPDATE
    API->>DB: INSERT bed_allocations(active_bed_id=bed); UPDATE beds SET status=RESERVED
    API->>DB: INSERT bed_status_logs + audit_logs; COMMIT
    API-->>N: 201 分配记录
    N->>API: POST /allocations/{id}/admit
    API->>DB: status=ADMITTED / beds.status=OCCUPIED
    N->>API: POST /allocations/{id}/discharge
    API->>DB: status=DISCHARGED / beds.status=CLEANING
    N->>API: POST /beds/{bed_id}/release
    API->>DB: beds.status=AVAILABLE
```

## 床位状态机

```mermaid
stateDiagram-v2
    [*] --> AVAILABLE
    AVAILABLE --> RESERVED : 预占用（分配）
    RESERVED --> OCCUPIED : 办理入住
    RESERVED --> AVAILABLE : 取消预占用
    OCCUPIED --> CLEANING : 办理出院
    CLEANING --> AVAILABLE : 床位释放
    AVAILABLE --> MAINTENANCE : 报修
    CLEANING --> MAINTENANCE : 报修
    MAINTENANCE --> AVAILABLE : 维修完成
```

任何不在此图中的流转都会返回 `409 ILLEGAL_STATE_TRANSITION`。

## 角色与权限矩阵

| 操作 | ADMIN | DOCTOR | NURSE | VIEWER |
| --- | :---: | :---: | :---: | :---: |
| 登录 / 查看看板 / 查看列表 | ✅ | ✅ | ✅ | ✅ |
| 开具住院证 | ✅ | ✅ | — | — |
| 预入院登记 | ✅ | ✅ | ✅ | — |
| 查看床位推荐 | ✅ | ✅ | ✅ | ✅ |
| 预占用 / 入住 / 出院 / 释放 | ✅ | — | ✅ | — |
| 基础数据维护（科室/病房/床位/医生） | ✅ | — | — | — |
| 新增/修改患者 | ✅ | — | ✅ | — |
| 查看患者明文信息 | ✅ | — | — | — |
| 查看审计日志 | ✅ | — | — | — |

越权访问返回 `403 PERMISSION_DENIED`，并写入一条 `result=FAILURE` 的审计记录。
