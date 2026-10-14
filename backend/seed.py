"""初始化演示数据。

用法：
    python seed.py            # 清空并写入演示数据
    python seed.py --no-reset # 追加（默认仍会先清空业务表）

全部数据均为**虚构**，不包含任何真实患者/医疗数据。
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import get_engine, get_session_factory
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.enums import (
    AdmissionRequestStatus,
    AllocationMode,
    AllocationStatus,
    BedStatus,
    BedType,
    DepositStatus,
    Gender,
    GenderLimit,
    PatientPriority,
    UserRole,
)
from app.models.facility import Bed, Department, Ward
from app.models.patient import Patient
from app.models.user import Doctor, User

TABLES_IN_DELETE_ORDER = [
    "allocation_idempotency",
    "bed_status_logs",
    "bed_allocations",
    "preadmissions",
    "admission_requests",
    "beds",
    "wards",
    "doctors",
    "patients",
    "departments",
    "users",
    "audit_logs",
]


def reset_data() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in TABLES_IN_DELETE_ORDER:
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    print("[seed] 已清空业务表")


def main() -> None:
    reset_data()
    db = get_session_factory()()

    try:
        # ------------------------------------------------------------------ #
        # 用户
        # ------------------------------------------------------------------ #
        users = {
            "admin": User(
                username="admin",
                hashed_password=hash_password("admin123"),
                full_name="系统管理员",
                role=UserRole.ADMIN,
            ),
            "doctor01": User(
                username="doctor01",
                hashed_password=hash_password("doctor123"),
                full_name="张明",
                role=UserRole.DOCTOR,
            ),
            "doctor02": User(
                username="doctor02",
                hashed_password=hash_password("doctor123"),
                full_name="李慧",
                role=UserRole.DOCTOR,
            ),
            "nurse01": User(
                username="nurse01",
                hashed_password=hash_password("nurse123"),
                full_name="王芳",
                role=UserRole.NURSE,
            ),
            "nurse02": User(
                username="nurse02",
                hashed_password=hash_password("nurse123"),
                full_name="赵强",
                role=UserRole.NURSE,
            ),
            "viewer01": User(
                username="viewer01",
                hashed_password=hash_password("viewer123"),
                full_name="陈静",
                role=UserRole.VIEWER,
            ),
        }
        db.add_all(users.values())
        db.flush()

        # ------------------------------------------------------------------ #
        # 科室
        # ------------------------------------------------------------------ #
        dept_specs = [
            ("CARD", "心血管内科", "急危重症心血管患者收治", 1, 0, 0),
            ("RESP", "呼吸与危重症医学科", "呼吸道疾病与呼吸支持", 2, 0, 0),
            ("ORTH", "骨科", "创伤与关节置换", 3, 0, 0),
            ("INF", "感染性疾病科", "法定传染病与隔离收治", 5, 50, 50),
            ("PED", "儿科", "儿童常见病", 2, 60, 0),
        ]
        depts: dict[str, Department] = {}
        for code, name, desc, floor, ax, ay in dept_specs:
            d = Department(
                code=code,
                name=name,
                description=desc,
                anchor_floor=floor,
                anchor_x=ax,
                anchor_y=ay,
            )
            db.add(d)
            depts[code] = d
        db.flush()

        # ------------------------------------------------------------------ #
        # 医生
        # ------------------------------------------------------------------ #
        doctors = {
            "d1": Doctor(
                name="张明", department_id=depts["CARD"].id, title="主任医师",
                phone="13900000001", user_id=users["doctor01"].id,
            ),
            "d2": Doctor(
                name="李慧", department_id=depts["RESP"].id, title="副主任医师",
                phone="13900000002", user_id=users["doctor02"].id,
            ),
            "d3": Doctor(name="刘伟", department_id=depts["ORTH"].id, title="主治医师", phone="13900000003"),
            "d4": Doctor(name="孙燕", department_id=depts["INF"].id, title="主任医师", phone="13900000004"),
            "d5": Doctor(name="周涛", department_id=depts["PED"].id, title="主治医师", phone="13900000005"),
        }
        db.add_all(doctors.values())
        db.flush()

        # ------------------------------------------------------------------ #
        # 病房与床位
        # ------------------------------------------------------------------ #
        ward_specs = [
            # (病房号, 名称, 科室, 楼层, 基准x, 基准y, 床位数, 床位规格描述)
            ("C-101", "心内一病房", "CARD", 1, 6, 6, 4),
            ("C-102", "心内二病房", "CARD", 1, 18, 6, 4),
            ("C-ICU", "心内监护单元", "CARD", 1, 2, 2, 3),
            ("R-201", "呼吸一病房", "RESP", 2, 8, 10, 4),
            ("R-202", "呼吸二病房", "RESP", 2, 22, 10, 4),
            ("R-ISO", "呼吸道隔离病房", "RESP", 2, 34, 10, 2),
            ("O-301", "骨科女病房", "ORTH", 3, 10, 8, 4),
            ("O-302", "骨科男病房", "ORTH", 3, 25, 8, 4),
            ("I-501", "感染科隔离一区", "INF", 5, 55, 55, 4),
            ("I-502", "感染科隔离二区", "INF", 5, 62, 55, 3),
            ("P-201", "儿科一病房", "PED", 2, 62, 6, 4),
            ("P-202", "儿科二病房", "PED", 2, 70, 6, 4),
        ]
        wards: dict[str, Ward] = {}
        ward_origin: dict[str, tuple[int, int]] = {}
        for code, name, dept_code, floor, bx, by, _ in ward_specs:
            w = Ward(
                code=code,
                name=name,
                department_id=depts[dept_code].id,
                building="住院楼A座",
                floor=floor,
            )
            db.add(w)
            wards[code] = w
            ward_origin[code] = (bx, by)
        db.flush()

        # 床位规格：(病房号, 床位数, 床型, 性别限制, 日费用, 是否隔离)
        bed_specs = [
            # 心内科
            ("C-101", 2, BedType.NORMAL, GenderLimit.ANY, Decimal("120.00")),
            ("C-101", 2, BedType.NORMAL, GenderLimit.MALE, Decimal("120.00")),
            ("C-102", 2, BedType.NORMAL, GenderLimit.ANY, Decimal("100.00")),
            ("C-102", 1, BedType.NORMAL, GenderLimit.MALE, Decimal("100.00")),
            ("C-102", 1, BedType.NORMAL, GenderLimit.FEMALE, Decimal("100.00")),
            ("C-ICU", 3, BedType.MONITOR, GenderLimit.ANY, Decimal("380.00")),
            # 呼吸内科
            ("R-201", 4, BedType.NORMAL, GenderLimit.ANY, Decimal("110.00")),
            ("R-202", 2, BedType.NORMAL, GenderLimit.ANY, Decimal("95.00")),
            ("R-202", 1, BedType.NORMAL, GenderLimit.MALE, Decimal("95.00")),
            ("R-202", 1, BedType.NORMAL, GenderLimit.FEMALE, Decimal("95.00")),
            ("R-ISO", 2, BedType.ISOLATION, GenderLimit.ANY, Decimal("220.00")),
            # 骨科
            ("O-301", 4, BedType.NORMAL, GenderLimit.FEMALE, Decimal("130.00")),
            ("O-302", 4, BedType.NORMAL, GenderLimit.MALE, Decimal("130.00")),
            # 感染科（全部隔离床）
            ("I-501", 4, BedType.ISOLATION, GenderLimit.ANY, Decimal("260.00")),
            ("I-502", 2, BedType.ISOLATION, GenderLimit.ANY, Decimal("260.00")),
            ("I-502", 1, BedType.ISOLATION, GenderLimit.FEMALE, Decimal("260.00")),
            # 儿科
            ("P-201", 4, BedType.NORMAL, GenderLimit.ANY, Decimal("140.00")),
            ("P-202", 4, BedType.NORMAL, GenderLimit.ANY, Decimal("140.00")),
        ]

        beds: dict[str, Bed] = {}
        ward_counters: dict[str, int] = {}
        for ward_code, count, bed_type, gender_limit, rate in bed_specs:
            ward = wards[ward_code]
            bx, by = ward_origin[ward_code]
            for _ in range(count):
                ward_counters[ward_code] = ward_counters.get(ward_code, 0) + 1
                idx = ward_counters[ward_code]
                code = f"{ward_code}-{idx:02d}"
                bed = Bed(
                    code=code,
                    ward_id=ward.id,
                    department_id=ward.department_id,
                    bed_type=bed_type,
                    gender_limit=gender_limit,
                    is_isolation=bed_type == BedType.ISOLATION,
                    floor=ward.floor,
                    # 以病房基准坐标铺开一个 4 列的网格，便于距离评分产生差异
                    position_x=bx + ((idx - 1) % 4) * 3,
                    position_y=by + ((idx - 1) // 4) * 3,
                    daily_rate=rate,
                    status=BedStatus.AVAILABLE,
                )
                beds[code] = bed
                db.add(bed)
        db.flush()

        # ------------------------------------------------------------------ #
        # 患者（全部虚构）
        # ------------------------------------------------------------------ #
        patient_specs = [
            ("张伟", Gender.MALE, "1972-03-12", "A"),
            ("李娜", Gender.FEMALE, "1985-07-21", "O"),
            ("王强", Gender.MALE, "1960-11-02", "B"),
            ("刘敏", Gender.FEMALE, "1993-01-15", "AB"),
            ("陈建国", Gender.MALE, "1955-05-30", "A"),
            ("杨丽", Gender.FEMALE, "1978-09-09", "O"),
            ("赵磊", Gender.MALE, "1988-12-25", "B"),
            ("孙晓", Gender.FEMALE, "2001-04-18", "A"),
            ("周涛", Gender.MALE, "1967-08-08", "O"),
            ("吴静", Gender.FEMALE, "1990-06-06", "AB"),
            ("郑海", Gender.MALE, "1975-02-14", "A"),
            ("马雅", Gender.FEMALE, "1982-10-03", "B"),
            ("何俊", Gender.MALE, "1999-09-19", "O"),
            ("冯雪", Gender.FEMALE, "1970-12-01", "A"),
            ("许峰", Gender.MALE, "1963-07-07", "B"),
            ("程蕾", Gender.FEMALE, "1996-03-27", "O"),
            ("卢博", Gender.MALE, "2008-11-11", "A"),
            ("苏晴", Gender.FEMALE, "2012-05-05", "O"),
            ("高翔", Gender.MALE, "1948-01-20", "AB"),
            ("邓丽", Gender.FEMALE, "1957-04-04", "A"),
        ]
        patients: list[Patient] = []
        for idx, (name, gender, birth, blood) in enumerate(patient_specs, start=1):
            p = Patient(
                medical_record_no=f"MR{idx:06d}",
                name=name,
                gender=gender,
                birth_date=date.fromisoformat(birth),
                id_card=f"4201{idx:04d}19{birth[2:4]}{birth[5:7]}{birth[8:10]}{idx:04d}"[:18],
                phone=f"138{idx:08d}",
                address=f"湖北省武汉市示例区示例路{idx}号（虚构）",
                blood_type=blood,
                is_infectious=idx in (13, 16),
                allergy="青霉素过敏" if idx % 5 == 0 else None,
            )
            patients.append(p)
            db.add(p)
        db.flush()

        def P(i: int) -> Patient:
            return patients[i - 1]

        # ------------------------------------------------------------------ #
        # 住院证 + 预入院 + 分配（构造多种状态）
        # ------------------------------------------------------------------ #
        now = datetime.now()
        seq = 0
        today = now.strftime("%Y%m%d")

        def new_request(
            patient: Patient,
            dept_code: str,
            doctor_key: str,
            priority: PatientPriority,
            isolation: bool,
            diagnosis: str,
            status: AdmissionRequestStatus,
            ward_code: str | None = None,
        ) -> AdmissionRequest:
            nonlocal seq
            seq += 1
            req = AdmissionRequest(
                certificate_no=f"ZY{today}{seq:04d}",
                patient_id=patient.id,
                department_id=depts[dept_code].id,
                doctor_id=doctors[doctor_key].id,
                priority=priority,
                isolation_required=isolation,
                infection_type="呼吸道传染病（示例）" if isolation else None,
                diagnosis=diagnosis,
                preferred_ward_id=wards[ward_code].id if ward_code else None,
                status=status,
                issued_at=now - timedelta(hours=seq),
            )
            db.add(req)
            db.flush()
            return req

        def new_preadmission(req: AdmissionRequest, amount: str, paid: bool, seq_no: int) -> Preadmission:
            pre = Preadmission(
                admission_request_id=req.id,
                queue_no=f"Q{today}{seq_no:04d}",
                queue_sequence=seq_no,
                contact_phone=f"139{seq_no:08d}",
                emergency_contact="家属（虚构）",
                emergency_phone=f"137{seq_no:08d}",
                deposit_amount=Decimal(amount),
                deposit_status=DepositStatus.PAID if paid else DepositStatus.PENDING,
                deposit_ref_no=f"SIM-PAY-{today}{seq_no:02d}" if paid else None,
                supplement={"陪护": "1人", "既往史": "无特殊（示例）"},
                supplement_notes="已完成入院宣教（示例）",
                registered_by=users["nurse01"].id,
                registered_at=now - timedelta(hours=seq_no),
            )
            db.add(pre)
            db.flush()
            return pre

        def occupy(req: AdmissionRequest, bed_code: str, status: str, mode: AllocationMode = AllocationMode.RECOMMENDED):
            bed = beds[bed_code]
            alloc = BedAllocation(
                admission_request_id=req.id,
                patient_id=req.patient_id,
                bed_id=bed.id,
                active_bed_id=bed.id,
                mode=mode,
                score=Decimal("88.50") if mode == AllocationMode.RECOMMENDED else None,
                reason="演示数据初始化",
                status=AllocationStatus(status),
                operator_id=users["nurse01"].id,
                reserved_at=now - timedelta(hours=6),
            )
            if status == "ADMITTED":
                alloc.admitted_at = now - timedelta(hours=4)
                bed.status = BedStatus.OCCUPIED
                req.status = AdmissionRequestStatus.ADMITTED
            else:
                bed.status = BedStatus.RESERVED
            db.add(alloc)
            db.flush()
            db.add(
                BedStatusLog(
                    bed_id=bed.id,
                    from_status=BedStatus.AVAILABLE.value,
                    to_status=bed.status.value,
                    reason="演示数据初始化",
                    allocation_id=alloc.id,
                    admission_request_id=req.id,
                    operator_id=users["nurse01"].id,
                )
            )
            return alloc

        # --- 已入住（占用床位） ---
        r1 = new_request(P(1), "CARD", "d1", PatientPriority.SEVERE, False, "冠心病，需监护", AdmissionRequestStatus.ISSUED)
        new_preadmission(r1, "5000.00", True, 1)
        r1.status = AdmissionRequestStatus.ADMITTED
        occupy(r1, "C-101-01", "ADMITTED")

        r2 = new_request(P(3), "RESP", "d2", PatientPriority.NORMAL, False, "慢性阻塞性肺疾病", AdmissionRequestStatus.ISSUED)
        new_preadmission(r2, "3000.00", True, 2)
        r2.status = AdmissionRequestStatus.ADMITTED
        occupy(r2, "R-201-01", "ADMITTED")

        r3 = new_request(P(13), "INF", "d4", PatientPriority.CRITICAL, True, "疑似呼吸道传染病，需隔离", AdmissionRequestStatus.ISSUED)
        new_preadmission(r3, "8000.00", True, 3)
        r3.status = AdmissionRequestStatus.ADMITTED
        occupy(r3, "I-501-01", "ADMITTED")

        # --- 已预占用（未入住） ---
        r4 = new_request(P(5), "ORTH", "d3", PatientPriority.URGENT, False, "股骨颈骨折，拟行手术", AdmissionRequestStatus.ISSUED)
        new_preadmission(r4, "6000.00", True, 4)
        occupy(r4, "O-302-01", "RESERVED")

        r5 = new_request(P(9), "CARD", "d1", PatientPriority.URGENT, False, "心律失常", AdmissionRequestStatus.ISSUED)
        new_preadmission(r5, "4000.00", False, 5)
        r5.status = AdmissionRequestStatus.PRE_ADMITTED
        occupy(r5, "C-ICU-01", "RESERVED")

        # --- 出院后清洁中的床位 ---
        r6 = new_request(P(15), "PED", "d5", PatientPriority.MILD, False, "急性上呼吸道感染", AdmissionRequestStatus.ISSUED)
        new_preadmission(r6, "1500.00", True, 6)
        r6.status = AdmissionRequestStatus.ADMITTED
        a6 = occupy(r6, "P-201-01", "ADMITTED")
        a6.status = AllocationStatus.DISCHARGED
        a6.admitted_at = now - timedelta(days=3)
        a6.discharged_at = now - timedelta(hours=2)
        a6.active_bed_id = None
        r6.status = AdmissionRequestStatus.COMPLETED
        beds["P-201-01"].status = BedStatus.CLEANING
        db.add(
            BedStatusLog(
                bed_id=beds["P-201-01"].id,
                from_status=BedStatus.OCCUPIED.value,
                to_status=BedStatus.CLEANING.value,
                reason="出院后清洁",
                allocation_id=a6.id,
                admission_request_id=r6.id,
                operator_id=users["nurse01"].id,
            )
        )

        # --- 维护中的床位 ---
        beds["R-202-04"].status = BedStatus.MAINTENANCE
        db.add(
            BedStatusLog(
                bed_id=beds["R-202-04"].id,
                from_status=BedStatus.AVAILABLE.value,
                to_status=BedStatus.MAINTENANCE.value,
                reason="床头设备检修",
                operator_id=users["admin"].id,
            )
        )

        # --- 待入院队列（可演示推荐与分配） ---
        queue_specs = [
            (P(2), "CARD", "d1", PatientPriority.NORMAL, False, "高血压待评估", "3000.00", False),
            (P(4), "ORTH", "d3", PatientPriority.NORMAL, False, "腰椎间盘突出", "4000.00", False),
            (P(6), "RESP", "d2", PatientPriority.SEVERE, False, "重症肺炎", "7000.00", True),
            (P(7), "ORTH", "d3", PatientPriority.URGENT, False, "胫骨骨折（男性患者，骨科男病房）", "5000.00", False),
            (P(8), "PED", "d5", PatientPriority.NORMAL, False, "支气管炎（女性儿童）", "2000.00", False),
            (P(11), "CARD", "d1", PatientPriority.CRITICAL, False, "急性心肌梗死，需监护床", "9000.00", True),
            (P(12), "INF", "d4", PatientPriority.SEVERE, True, "结核病，需负压隔离", "6000.00", False),
            (P(14), "ORTH", "d3", PatientPriority.MILD, False, "术后复查（女性患者）", "3000.00", False),
        ]
        for idx, (pat, dc, dk, pr, iso, diag, amount, paid) in enumerate(queue_specs, start=10):
            req = new_request(pat, dc, dk, pr, iso, diag, AdmissionRequestStatus.ISSUED)
            new_preadmission(req, amount, paid, idx)
            req.status = AdmissionRequestStatus.PRE_ADMITTED

        # --- 仅已开具、未预入院 ---
        new_request(P(16), "PED", "d5", PatientPriority.MILD, False, "儿童发热待查", AdmissionRequestStatus.ISSUED)

        # --- 草稿 ---
        new_request(P(17), "CARD", "d1", PatientPriority.NORMAL, False, "胸闷待查（草稿）", AdmissionRequestStatus.DRAFT)

        db.commit()

        # ------------------------------------------------------------------ #
        # 汇总输出
        # ------------------------------------------------------------------ #
        total_beds = db.query(Bed).count()
        available = db.query(Bed).filter(Bed.status == BedStatus.AVAILABLE).count()
        reserved = db.query(Bed).filter(Bed.status == BedStatus.RESERVED).count()
        occupied = db.query(Bed).filter(Bed.status == BedStatus.OCCUPIED).count()
        cleaning = db.query(Bed).filter(Bed.status == BedStatus.CLEANING).count()
        maintenance = db.query(Bed).filter(Bed.status == BedStatus.MAINTENANCE).count()
        pending = (
            db.query(Preadmission)
            .join(AdmissionRequest, AdmissionRequest.id == Preadmission.admission_request_id)
            .filter(AdmissionRequest.status == AdmissionRequestStatus.PRE_ADMITTED)
            .count()
        )
        print("[seed] 演示数据初始化完成")
        print(f"       科室 {db.query(Department).count()} 个 / 病房 {db.query(Ward).count()} 间")
        print(
            f"       床位 {total_beds} 张（空闲 {available} / 预占用 {reserved} / 已入住 {occupied} "
            f"/ 清洁 {cleaning} / 维护 {maintenance}）"
        )
        print(f"       患者 {db.query(Patient).count()} 人 / 医生 {db.query(Doctor).count()} 人 / 用户 {db.query(User).count()} 个")
        print(f"       住院证 {db.query(AdmissionRequest).count()} 张 / 待入院队列 {pending} 人")
        print("       演示账号：admin/admin123、doctor01/doctor123、nurse01/nurse123、viewer01/viewer123")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
