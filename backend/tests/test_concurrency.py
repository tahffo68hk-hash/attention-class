"""并发抢占测试。

**在真实 MySQL 上执行**（不依赖 SQLite 的锁行为）：
两个线程在同一时刻争抢同一张床位，期望恰好一个成功、一个失败，
床位最终只被一条活动分配记录占用。
"""

from __future__ import annotations

import threading

from sqlalchemy import func, select

from app.core.errors import BizError
from app.db.session import get_session_factory
from app.models.allocation import BedAllocation
from app.models.facility import Bed
from app.models.user import User
from app.services import allocation as allocation_service
from tests.conftest import make_request


def _reserve_worker(request_id, bed_id, operator_id, barrier, results, index):
    db = get_session_factory()()
    try:
        operator = db.get(User, operator_id)
        barrier.wait(timeout=10)  # 让两个线程尽可能同时进入
        alloc = allocation_service.reserve_bed(
            db, request_id=request_id, bed_id=bed_id, operator=operator
        )
        results[index] = ("OK", alloc.id)
    except BizError as exc:
        results[index] = ("BIZ", exc.code, exc.status_code)
    except Exception as exc:  # pragma: no cover - 仅在实现异常时触发
        results[index] = ("EXC", type(exc).__name__, str(exc)[:160])
    finally:
        db.close()


def test_two_threads_race_for_same_bed(client, ds):
    """两次并发竞争同一床位：恰好一个成功。"""
    req_a = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=1)
    req_b = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=2)
    bed_id = ds.bed("C-W1-01")
    operator_id = ds.users["nurse01"]

    results: dict[int, tuple] = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(
            target=_reserve_worker, args=(req_a, bed_id, operator_id, barrier, results, 0)
        ),
        threading.Thread(
            target=_reserve_worker, args=(req_b, bed_id, operator_id, barrier, results, 1)
        ),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"两个线程都应返回结果，实际: {results}"

    ok = [r for r in results.values() if r[0] == "OK"]
    failed = [r for r in results.values() if r[0] != "OK"]
    assert len(ok) == 1, f"应恰好一个成功，实际: {results}"
    assert len(failed) == 1, f"应恰好一个失败，实际: {results}"

    kind = failed[0][0]
    assert kind in {"BIZ"}, f"失败方应为业务异常（409），实际: {failed[0]}"
    assert failed[0][1] in {"BED_NOT_AVAILABLE", "BED_DOUBLE_BOOKED"}, failed[0]
    assert failed[0][2] == 409

    # 数据库状态：床位预占用，且只有一条活动占用记录
    db = get_session_factory()()
    try:
        assert str(db.get(Bed, bed_id).status) == "RESERVED"
        active = db.execute(
            select(func.count(BedAllocation.id)).where(BedAllocation.active_bed_id == bed_id)
        ).scalar_one()
        assert active == 1, f"活动占用记录必须恰好 1 条，实际 {active}"

        total = db.execute(
            select(func.count(BedAllocation.id)).where(BedAllocation.bed_id == bed_id)
        ).scalar_one()
        assert total == 1, "失败方不得留下任何分配记录"
    finally:
        db.close()


def test_unique_index_blocks_duplicate_active_allocation(client, ds):
    """数据库兜底：active_bed_id 唯一索引拒绝第二条活动占用记录。"""
    from sqlalchemy.exc import IntegrityError

    from app.models.allocation import BedAllocation as BA
    from app.models.enums import AllocationMode, AllocationStatus

    req_a = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=3)
    req_b = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=4)
    bed_id = ds.bed("C-W1-04")

    db = get_session_factory()()
    try:
        db.add(
            BA(
                admission_request_id=req_a,
                patient_id=ds.patients["男患者甲"],
                bed_id=bed_id,
                active_bed_id=bed_id,
                mode=AllocationMode.MANUAL,
                status=AllocationStatus.RESERVED,
            )
        )
        db.commit()

        db.add(
            BA(
                admission_request_id=req_b,
                patient_id=ds.patients["男患者丙"],
                bed_id=bed_id,
                active_bed_id=bed_id,
                mode=AllocationMode.MANUAL,
                status=AllocationStatus.RESERVED,
            )
        )
        try:
            db.commit()
            raise AssertionError("唯一索引未生效：第二条活动占用记录被写入")
        except IntegrityError:
            db.rollback()
    finally:
        db.close()


def test_concurrent_race_via_api_returns_conflict(client, ds, nurse_headers):
    """API 层顺序抢占：第二次请求返回 409 BED_NOT_AVAILABLE。"""
    req_a = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=5)
    req_b = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=6)
    bed_id = ds.bed("C-ICU-01")

    first = client.post(
        "/api/v1/allocations",
        json={"admission_request_id": req_a, "bed_id": bed_id},
        headers=nurse_headers,
    )
    second = client.post(
        "/api/v1/allocations",
        json={"admission_request_id": req_b, "bed_id": bed_id},
        headers=nurse_headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "BED_NOT_AVAILABLE"
