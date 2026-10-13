"""pytest 公共夹具：真实 MySQL 测试库 + Alembic 迁移 + 受控数据集。

并发与状态测试**在 MySQL 上执行**（127.0.0.1:3307 的 hospital_test 库），
不使用 SQLite 的锁行为代替。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402

# 让整个应用（含 Alembic env.py）指向测试库
settings.DATABASE_URL = settings.TEST_DATABASE_URL

from app.core.security import hash_password  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.admission import AdmissionRequest, Preadmission  # noqa: E402
from app.models.enums import (  # noqa: E402
    AdmissionRequestStatus,
    BedStatus,
    BedType,
    DepositStatus,
    Gender,
    GenderLimit,
    PatientPriority,
    UserRole,
)
from app.models.facility import Bed, Department, Ward  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.models.user import Doctor, User  # noqa: E402

db_session.reset_engine()


# --------------------------------------------------------------------------- #
# 表结构：每次测试会话用 Alembic 从零建表（同时验证迁移脚本本身）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def prepare_schema():
    from alembic import command
    from alembic.config import Config

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE()"
            )
        ).fetchall()
        for (table,) in rows:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")
    yield


TABLES = [
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


def _truncate_all() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in TABLES:
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


# --------------------------------------------------------------------------- #
# 数据集
# --------------------------------------------------------------------------- #
@dataclass
class Dataset:
    departments: dict[str, int] = field(default_factory=dict)
    wards: dict[str, int] = field(default_factory=dict)
    beds: dict[str, int] = field(default_factory=dict)
    patients: dict[str, int] = field(default_factory=dict)
    doctors: dict[str, int] = field(default_factory=dict)
    users: dict[str, int] = field(default_factory=dict)

    def bed(self, code: str) -> int:
        return self.beds[code]


def build_dataset() -> Dataset:
    """构造受控演示数据集：覆盖性别限制、隔离床、监护床、不同距离与价格。"""
    db = get_session_factory()()
    ds = Dataset()
    try:
        # ---- 科室 ----
        dept_specs = [
            ("CARD", "心血管内科", 1, 0, 0),
            ("ORTH", "骨科", 3, 0, 0),
            ("INF", "感染性疾病科", 5, 50, 50),
            ("PED", "儿科", 2, 60, 0),
        ]
        for code, name, floor, ax, ay in dept_specs:
            d = Department(code=code, name=name, anchor_floor=floor, anchor_x=ax, anchor_y=ay)
            db.add(d)
            db.flush()
            ds.departments[code] = d.id

        # ---- 病房 ----
        ward_specs = [
            ("C-W1", "心内一病房", "CARD", 1, 10, 10),
            ("C-W2", "心内男病房", "CARD", 1, 34, 10),
            ("C-ICU", "心内监护单元", "CARD", 1, 2, 2),
            ("O-W1", "骨科女病房", "ORTH", 3, 10, 10),
            ("I-W1", "感染科隔离病房", "INF", 5, 55, 55),
            ("P-W1", "儿科病房", "PED", 2, 62, 6),
        ]
        for code, name, dept, floor, bx, by in ward_specs:
            w = Ward(
                code=code,
                name=name,
                department_id=ds.departments[dept],
                floor=floor,
                building="住院楼A座",
            )
            db.add(w)
            db.flush()
            ds.wards[code] = w.id

        # ---- 床位 ----
        bed_specs = [
            # (病房, 床号, 床型, 性别限制, x, y, 日费用)
            ("C-W1", "C-W1-01", BedType.NORMAL, GenderLimit.ANY, 10, 10, "100.00"),
            ("C-W1", "C-W1-02", BedType.NORMAL, GenderLimit.ANY, 13, 10, "100.00"),
            ("C-W1", "C-W1-03", BedType.NORMAL, GenderLimit.FEMALE, 16, 10, "150.00"),
            ("C-W1", "C-W1-04", BedType.NORMAL, GenderLimit.ANY, 19, 10, "150.00"),
            ("C-W2", "C-W2-01", BedType.NORMAL, GenderLimit.MALE, 34, 10, "200.00"),
            ("C-W2", "C-W2-02", BedType.NORMAL, GenderLimit.MALE, 37, 10, "200.00"),
            ("C-ICU", "C-ICU-01", BedType.MONITOR, GenderLimit.ANY, 2, 2, "400.00"),
            ("C-ICU", "C-ICU-02", BedType.MONITOR, GenderLimit.ANY, 4, 2, "400.00"),
            ("O-W1", "O-W1-01", BedType.NORMAL, GenderLimit.FEMALE, 10, 10, "120.00"),
            ("O-W1", "O-W1-02", BedType.NORMAL, GenderLimit.FEMALE, 13, 10, "120.00"),
            ("O-W1", "O-W1-03", BedType.NORMAL, GenderLimit.FEMALE, 16, 10, "120.00"),
            ("I-W1", "I-W1-01", BedType.ISOLATION, GenderLimit.ANY, 55, 55, "260.00"),
            ("I-W1", "I-W1-02", BedType.ISOLATION, GenderLimit.ANY, 58, 55, "260.00"),
            ("I-W1", "I-W1-03", BedType.ISOLATION, GenderLimit.FEMALE, 61, 55, "260.00"),
            ("P-W1", "P-W1-01", BedType.NORMAL, GenderLimit.ANY, 62, 6, "140.00"),
            ("P-W1", "P-W1-02", BedType.NORMAL, GenderLimit.ANY, 65, 6, "140.00"),
        ]
        for ward_code, code, bed_type, gender_limit, px, py, rate in bed_specs:
            ward = db.get(Ward, ds.wards[ward_code])
            bed = Bed(
                code=code,
                ward_id=ward.id,
                department_id=ward.department_id,
                bed_type=bed_type,
                gender_limit=gender_limit,
                is_isolation=bed_type == BedType.ISOLATION,
                floor=ward.floor,
                position_x=px,
                position_y=py,
                daily_rate=Decimal(rate),
                status=BedStatus.AVAILABLE,
            )
            db.add(bed)
            db.flush()
            ds.beds[code] = bed.id

        # ---- 用户 ----
        user_specs = [
            ("admin", "admin123", "系统管理员", UserRole.ADMIN),
            ("doctor01", "doctor123", "张明", UserRole.DOCTOR),
            ("nurse01", "nurse123", "王芳", UserRole.NURSE),
            ("viewer01", "viewer123", "陈静", UserRole.VIEWER),
        ]
        for username, password, full_name, role in user_specs:
            u = User(
                username=username,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=role,
            )
            db.add(u)
            db.flush()
            ds.users[username] = u.id

        # ---- 医生 ----
        doc = Doctor(
            name="张明",
            department_id=ds.departments["CARD"],
            title="主任医师",
            user_id=ds.users["doctor01"],
        )
        db.add(doc)
        db.flush()
        ds.doctors["张明"] = doc.id

        # ---- 患者（全部虚构） ----
        patient_specs = [
            ("男患者甲", Gender.MALE),
            ("女患者乙", Gender.FEMALE),
            ("男患者丙", Gender.MALE),
            ("男童丁", Gender.MALE),
        ]
        for idx, (name, gender) in enumerate(patient_specs, start=1):
            p = Patient(
                medical_record_no=f"MR{idx:06d}",
                name=name,
                gender=gender,
                birth_date=date(1980 + idx, 1, 1),
                phone=f"1380000000{idx}",
                id_card=f"42010119800{idx}01{idx:04d}",
            )
            db.add(p)
            db.flush()
            ds.patients[name] = p.id

        db.commit()
    finally:
        db.close()
    return ds


def make_request(
    ds: Dataset,
    *,
    patient_name: str,
    department_code: str,
    priority: str = PatientPriority.NORMAL.value,
    isolation_required: bool = False,
    status: str = AdmissionRequestStatus.PRE_ADMITTED.value,
    preferred_ward_code: str | None = None,
    with_preadmission: bool = True,
    seq: int = 1,
) -> int:
    """直接落库构造一张住院证（含预入院登记），返回住院证 ID。"""
    db = get_session_factory()()
    try:
        now = datetime.now()
        req = AdmissionRequest(
            certificate_no=f"TEST{now.strftime('%H%M%S')}{seq:03d}",
            patient_id=ds.patients[patient_name],
            department_id=ds.departments[department_code],
            doctor_id=ds.doctors["张明"],
            priority=PatientPriority(priority),
            isolation_required=isolation_required,
            diagnosis="测试用诊断（虚构）",
            preferred_ward_id=ds.wards[preferred_ward_code] if preferred_ward_code else None,
            status=AdmissionRequestStatus(status),
            issued_at=now - timedelta(hours=seq),
        )
        db.add(req)
        db.flush()
        if with_preadmission:
            db.add(
                Preadmission(
                    admission_request_id=req.id,
                    queue_no=f"QTEST{now.strftime('%H%M%S')}{seq:03d}",
                    queue_sequence=seq,
                    deposit_amount=Decimal("2000.00"),
                    deposit_status=DepositStatus.PAID,
                    registered_by=ds.users["nurse01"],
                    registered_at=now,
                )
            )
        db.commit()
        return req.id
    finally:
        db.close()


def set_bed_status(bed_id: int, status: str) -> None:
    db = get_session_factory()()
    try:
        bed = db.get(Bed, bed_id)
        bed.status = BedStatus(status)
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ds() -> Dataset:
    """每个测试前重置数据并构造受控数据集。"""
    _truncate_all()
    return build_dataset()


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


def auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, ds) -> dict[str, str]:
    return auth_headers(client, "admin", "admin123")


@pytest.fixture()
def doctor_headers(client, ds) -> dict[str, str]:
    return auth_headers(client, "doctor01", "doctor123")


@pytest.fixture()
def nurse_headers(client, ds) -> dict[str, str]:
    return auth_headers(client, "nurse01", "nurse123")


@pytest.fixture()
def viewer_headers(client, ds) -> dict[str, str]:
    return auth_headers(client, "viewer01", "viewer123")
