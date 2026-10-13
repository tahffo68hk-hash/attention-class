# E-R 图

> 下表为**原型草案**，用于跑通端到端演示；正式业务表结构待设计确认后定稿。

## 实体关系图（Mermaid）

```mermaid
erDiagram
    users ||--o| doctors : "登录账号关联医生档案"
    departments ||--o{ doctors : "所属科室"
    departments ||--o{ wards : "下辖病房"
    departments ||--o{ beds : "床位的收治科室"
    departments ||--o{ admission_requests : "收治科室"
    wards ||--o{ beds : "包含床位"
    wards ||--o{ admission_requests : "患者期望病房"
    patients ||--o{ admission_requests : "患者"
    patients ||--o{ bed_allocations : "患者"
    doctors ||--o{ admission_requests : "开具住院证"
    admission_requests ||--o| preadmissions : "预入院登记(1:1)"
    admission_requests ||--o{ bed_allocations : "分配记录"
    beds ||--o{ bed_allocations : "被分配"
    beds ||--o{ bed_status_logs : "状态流水"
    bed_allocations ||--o{ bed_status_logs : "触发状态变化"
    users ||--o{ bed_allocations : "操作人"
    users ||--o{ audit_logs : "审计主体"

    users {
        int id PK
        varchar username UK "登录名"
        varchar hashed_password
        varchar full_name
        enum role "ADMIN/DOCTOR/NURSE/VIEWER"
        bool is_active
        datetime last_login_at
    }

    doctors {
        int id PK
        int user_id FK "可空，关联 users"
        varchar name
        int department_id FK
        varchar title "职称"
        varchar phone
    }

    departments {
        int id PK
        varchar code UK "科室编码"
        varchar name
        int anchor_floor "护士站楼层"
        int anchor_x "护士站 X"
        int anchor_y "护士站 Y"
    }

    wards {
        int id PK
        varchar code UK "病房号"
        varchar name
        int department_id FK
        varchar building
        int floor
    }

    beds {
        int id PK
        varchar code UK "床位号"
        int ward_id FK
        int department_id FK
        enum bed_type "NORMAL/ISOLATION/MONITOR"
        enum gender_limit "MALE/FEMALE/ANY"
        bool is_isolation "隔离属性"
        int floor "楼层"
        int position_x "位置 X"
        int position_y "位置 Y"
        enum status "AVAILABLE/RESERVED/OCCUPIED/CLEANING/MAINTENANCE"
        decimal daily_rate
    }

    patients {
        int id PK
        varchar medical_record_no UK "病案号"
        varchar name
        enum gender "MALE/FEMALE"
        date birth_date
        varchar id_card "证件号"
        varchar phone
        bool is_infectious
    }

    admission_requests {
        int id PK
        varchar certificate_no UK "住院证编号"
        int patient_id FK
        int department_id FK
        int doctor_id FK
        enum priority "CRITICAL/SEVERE/URGENT/NORMAL/MILD"
        bool isolation_required "隔离需求"
        varchar infection_type
        int preferred_ward_id FK
        enum status "DRAFT/ISSUED/PRE_ADMITTED/ADMITTED/COMPLETED/CANCELLED"
        datetime issued_at
    }

    preadmissions {
        int id PK
        int admission_request_id FK "UK，1:1"
        varchar queue_no UK "排队号"
        int queue_sequence "队列序号"
        decimal deposit_amount "预交金（模拟）"
        enum deposit_status "PENDING/PAID/REFUNDED"
        varchar deposit_ref_no "模拟流水号"
        json supplement
    }

    bed_allocations {
        int id PK
        int admission_request_id FK
        int patient_id FK
        int bed_id FK
        int active_bed_id UK "活动占用标记（并发保护）"
        enum mode "RECOMMENDED/MANUAL"
        decimal score
        json score_detail "得分明细"
        text reason
        enum status "RESERVED/ADMITTED/DISCHARGED/CANCELLED"
        datetime reserved_at
        datetime admitted_at
        datetime discharged_at
        datetime released_at
    }

    bed_status_logs {
        int id PK
        int bed_id FK
        enum from_status
        enum to_status
        varchar reason
        int allocation_id FK
        int admission_request_id FK
        int operator_id FK
    }

    audit_logs {
        int id PK
        int user_id
        varchar username
        varchar role
        varchar action
        varchar object_type
        varchar object_id
        enum result "SUCCESS/FAILURE"
        json detail
        varchar ip
    }
```

## 索引设计

| 表 | 索引 | 目的 |
| --- | --- | --- |
| `beds` | `ix_beds_dept_status(department_id, status)` | 推荐时按科室 + 状态过滤 |
| `beds` | `ix_beds_status_isolation(status, is_isolation)` | 隔离床可用量统计 |
| `beds` | `ix_beds_ward_status(ward_id, status)` | 病房负载（空床率）计算 |
| `admission_requests` | `ix_admission_requests_dept_status` / `ix_admission_requests_priority` | 队列与看板筛选 |
| `bed_allocations` | `UNIQUE(active_bed_id)` | **并发防重复占用（核心）** |
| `bed_allocations` | `ix_allocations_status_time` | 分配记录列表与统计 |
| `bed_status_logs` | `ix_bed_status_logs_bed_time` | 床位流转时间线 |
| `audit_logs` | `ix_audit_logs_created` / `_user` / `_action` / `_object` | 审计检索 |

## 状态约束

| 对象 | 取值 | 合法流转 |
| --- | --- | --- |
| 床位 `beds.status` | AVAILABLE / RESERVED / OCCUPIED / CLEANING / MAINTENANCE | AVAILABLE→RESERVED\|MAINTENANCE；RESERVED→OCCUPIED\|AVAILABLE；OCCUPIED→CLEANING；CLEANING→AVAILABLE\|MAINTENANCE；MAINTENANCE→AVAILABLE |
| 住院证 `admission_requests.status` | DRAFT / ISSUED / PRE_ADMITTED / ADMITTED / COMPLETED / CANCELLED | DRAFT→ISSUED\|CANCELLED；ISSUED→PRE_ADMITTED\|CANCELLED；PRE_ADMITTED→ADMITTED\|CANCELLED；ADMITTED→COMPLETED |
| 分配 `bed_allocations.status` | RESERVED / ADMITTED / DISCHARGED / CANCELLED | RESERVED→ADMITTED\|CANCELLED；ADMITTED→DISCHARGED |

数据库级约束（MySQL 8.0.16+ 生效）：

```sql
CONSTRAINT ck_beds_isolation_consistent CHECK (
  (bed_type = 'ISOLATION' AND is_isolation = 1)
  OR (bed_type <> 'ISOLATION' AND is_isolation = 0)
);
```

约束在业务层通过 `BED_STATUS_TRANSITIONS` / `ADMISSION_REQUEST_TRANSITIONS` /
`ALLOCATION_TRANSITIONS` 三张流转表集中校验，非法流转统一返回
`409 ILLEGAL_STATE_TRANSITION`。

## 并发防重复占用

`bed_allocations.active_bed_id` 在分配处于 `RESERVED` / `ADMITTED` 时写入被占用床位 ID，
其余状态写 `NULL`。MySQL 唯一索引允许多个 `NULL`，因此：

* 同一床位最多只能存在一条活动占用记录 → 数据库层面拒绝重复占用；
* 历史记录不受影响，可无限累积。

配合业务层的 `SELECT ... FOR UPDATE` 行级锁，形成双重保护。
