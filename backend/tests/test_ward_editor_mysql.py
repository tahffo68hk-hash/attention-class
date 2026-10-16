"""正式床位管理接口的**真实 MySQL** 用例（hospital_test，127.0.0.1:3307）。

为什么另开一份：
`tests_ward_map/test_ward_editor.py` 跑在 SQLite，其 docstring 自己写明
「MySQL row-lock races must be retested in hospital_test」。本文件补上这段缺口——
事务边界、槽位唯一约束、`SELECT ... FOR UPDATE` 行锁并发、角色权限与同事务审计。

只使用虚构数据；不做任何演示库操作。
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import func, select

from app.api.v1.ward_map import get_ward_map
from app.core.errors import BizError
from app.db.session import get_session_factory
from app.models.audit import AuditLog
from app.models.enums import AuditAction, BedStatus, UserRole
from app.models.facility import Bed, BedSceneSlot
from app.models.user import User
from app.schemas.ward_editor import ManagedBedCreate, ManagedBedPose
from app.services import ward_editor as ops

BASE = "/api/v1/ward-map/managed-beds"


def payload(session, ds, code: str, slot: int, ward_code: str = "C-W1") -> dict:
    """构造管理员正式新增床位的请求体（复用同病房模板，评分坐标沿用模板）。"""
    template = session.get(Bed, ds.bed(f"{ward_code}-01"))
    return {
        "confirm": True,
        "code": code,
        "ward_id": template.ward_id,
        "scene_slot": slot,
        "rotation": 0,
        "template_bed_id": template.id,
        "bed_type": "NORMAL",
        "gender_limit": "ANY",
        "daily_rate": "88.00",
        "note": "课程原型（虚构）",
    }


def _admin(session) -> User:
    return session.scalar(select(User).where(User.role == UserRole.ADMIN))


# --------------------------------------------------------------------------- #
# 1. 生命周期：新增 → 幂等重放 → 停用 → 从态势图消失 → 恢复（槽位不变）
# --------------------------------------------------------------------------- #
def test_lifecycle_and_audit_on_mysql(client, admin_headers, ds):
    db = get_session_factory()()
    try:
        body = payload(db, ds, "WM-MYSQL-01", 8)
        beds_before = db.scalar(select(func.count(Bed.id)))
        audit_before = db.scalar(select(func.count(AuditLog.id)))

        first = client.post(BASE, json=body, headers=admin_headers)
        assert first.status_code == 201, first.text
        new_id = first.json()["id"]
        assert first.json()["scene_slot"] == 8 and first.json()["retired"] is False

        # 幂等：完全相同的请求重复提交不应产生第二张床
        again = client.post(BASE, json=body, headers=admin_headers)
        assert again.status_code == 201 and again.json()["id"] == new_id
        assert db.scalar(select(func.count(Bed.id))) == beds_before + 1

        # 业务写入与审计在同一事务提交：创建成功后必然留下 CREATE 审计。
        # 注意：幂等重放（第二次 POST）会**再**写一条 CREATE 审计——交付候选刻意
        # 「每个请求都留痕」，因此这里是 >= 1 而不是 == 1（已记入集成报告的已知偏差）。
        created_audits = db.scalars(
            select(AuditLog).where(
                AuditLog.object_type == "bed",
                AuditLog.object_id == new_id,
                AuditLog.action == AuditAction.CREATE.value,
            )
        ).all()
        assert len(created_audits) >= 1
        assert created_audits[0].detail.get("operation") == "CREATE"
        assert db.scalar(select(func.count(AuditLog.id))) > audit_before

        # 展示槽位独立于评分坐标：新增床沿用模板的 position_x/position_y
        template = db.get(Bed, ds.bed("C-W1-01"))
        created = db.get(Bed, new_id)
        assert (created.position_x, created.position_y) == (
            template.position_x,
            template.position_y,
        )

        # 态势图可见 → 停用后不可见 → 恢复后重新可见且槽位不变
        user = _admin(db)
        assert any(b.id == new_id for b in get_ward_map(db, user).beds)
        archived = client.post(
            f"{BASE}/{new_id}/archive",
            json={"confirm": True, "reason": "课程演示停用"},
            headers=admin_headers,
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["retired"] is True
        db.expire_all()
        assert not any(b.id == new_id for b in get_ward_map(db, user).beds)

        restored = client.post(
            f"{BASE}/{new_id}/restore",
            json={"confirm": True, "reason": "课程演示恢复"},
            headers=admin_headers,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["retired"] is False
        assert restored.json()["scene_slot"] == 8
        db.expire_all()
        assert any(b.id == new_id for b in get_ward_map(db, user).beds)
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 2. 停用只允许空闲/维护；占用/预占/清洁必须走正常流程
# --------------------------------------------------------------------------- #
def test_archive_denied_for_non_free_status_on_mysql(client, admin_headers, ds):
    db = get_session_factory()()
    try:
        body = payload(db, ds, "WM-MYSQL-02", 9)
        resp = client.post(BASE, json=body, headers=admin_headers)
        assert resp.status_code == 201, resp.text
        bed_id = resp.json()["id"]

        for status in (BedStatus.RESERVED, BedStatus.OCCUPIED, BedStatus.CLEANING):
            db.execute(Bed.__table__.update().where(Bed.id == bed_id).values(status=status))
            db.commit()
            denied = client.post(
                f"{BASE}/{bed_id}/archive",
                json={"confirm": True, "reason": "状态不允许"},
                headers=admin_headers,
            )
            assert denied.status_code == 409, (status, denied.text)
            assert denied.json()["code"] == "ILLEGAL_STATE_TRANSITION"
            db.expire_all()
            assert db.get(Bed, bed_id).retired_at is None
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 3. 槽位唯一：跨床位抢同一槽位必须 409，且不产生半成品写入
# --------------------------------------------------------------------------- #
def test_slot_conflict_is_rejected_without_partial_write(client, admin_headers, ds):
    db = get_session_factory()()
    try:
        a = client.post(BASE, json=payload(db, ds, "WM-MYSQL-03A", 3), headers=admin_headers)
        b = client.post(BASE, json=payload(db, ds, "WM-MYSQL-03B", 4), headers=admin_headers)
        assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
        bed_a, bed_b = a.json()["id"], b.json()["id"]

        slots_before = db.scalar(select(func.count(BedSceneSlot.id)))
        clash = client.put(
            f"{BASE}/{bed_b}/pose",
            json={"confirm": True, "ward_id": a.json()["ward_id"], "scene_slot": 3, "rotation": 90},
            headers=admin_headers,
        )
        assert clash.status_code == 409, clash.text
        db.expire_all()
        # 冲突被拒后：B 槽位未变、槽位行数未变、B 床位仍存在且未被停用
        assert db.scalar(select(BedSceneSlot.slot).where(BedSceneSlot.bed_id == bed_b)) == 4
        assert db.scalar(select(func.count(BedSceneSlot.id))) == slots_before
        assert db.get(Bed, bed_b).retired_at is None

        # 换到空闲槽位可以成功，且评分坐标不被展示槽位影响
        template = db.get(Bed, ds.bed("C-W1-01"))
        ok = client.put(
            f"{BASE}/{bed_b}/pose",
            json={"confirm": True, "ward_id": a.json()["ward_id"], "scene_slot": 9, "rotation": 90},
            headers=admin_headers,
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["scene_slot"] == 9 and ok.json()["rotation"] == 90
        db.expire_all()
        assert (db.get(Bed, bed_b).position_x, db.get(Bed, bed_b).position_y) == (
            template.position_x,
            template.position_y,
        )
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 4. 行锁并发：两个线程抢同一病房的同一槽位 → 恰好一个成功
# --------------------------------------------------------------------------- #
def _create_worker(body: dict, barrier, results, index: int) -> None:
    db = get_session_factory()()
    try:
        barrier.wait(timeout=15)
        bed = ops.create_bed(db, ManagedBedCreate.model_validate(body))
        db.commit()
        results[index] = ("OK", bed.id)
    except Exception as exc:  # noqa: BLE001 - 竞态下允许冲突/唯一约束失败
        db.rollback()
        results[index] = ("FAIL", type(exc).__name__, str(exc)[:160])
    finally:
        db.close()


def test_concurrent_create_same_slot_serializes_via_row_lock(ds):
    db = get_session_factory()()
    try:
        ward_id = db.get(Bed, ds.bed("C-W1-01")).ward_id
        template_id = ds.bed("C-W1-01")
        beds_before = db.scalar(select(func.count(Bed.id)))
        bodies = [
            {
                "confirm": True,
                "code": f"WM-RACE-{i}",
                "ward_id": ward_id,
                "scene_slot": 6,
                "rotation": 0,
                "template_bed_id": template_id,
                "bed_type": "NORMAL",
                "gender_limit": "ANY",
                "daily_rate": "88.00",
                "note": None,
            }
            for i in (1, 2)
        ]
        results: dict[int, tuple] = {}
        barrier = threading.Barrier(2)
        threads = [
            threading.Thread(target=_create_worker, args=(bodies[i], barrier, results, i))
            for i in (0, 1)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=40)
        assert len(results) == 2, f"两个线程都应返回结果：{results}"

        ok = [r for r in results.values() if r[0] == "OK"]
        bad = [r for r in results.values() if r[0] != "OK"]
        assert len(ok) == 1, f"同一槽位应恰好一个成功：{results}"
        assert len(bad) == 1, f"另一个必须被拒绝：{results}"
        # 失败方必须是可判定的业务/数据冲突，而不是静默通过
        assert bad[0][1] in {"ConflictError", "IntegrityError"}, results

        db.expire_all()
        assert db.scalar(select(func.count(Bed.id))) == beds_before + 1
        assert (
            db.scalar(
                select(func.count(BedSceneSlot.id)).where(
                    BedSceneSlot.ward_id == ward_id, BedSceneSlot.slot == 6
                )
            )
            == 1
        ), "同一病房槽位必须唯一"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 5. 权限：未登录 401；非 ADMIN 一律 403 且不写库；ADMIN 放行
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture_name", ["nurse_headers", "doctor_headers", "viewer_headers"])
def test_non_admin_cannot_touch_managed_beds(
    client, request, ds, fixture_name: str
):
    headers = request.getfixturevalue(fixture_name)
    db = get_session_factory()()
    try:
        body = payload(db, ds, f"WM-DENY-{fixture_name[:4]}", 11)
        beds_before = db.scalar(select(func.count(Bed.id)))

        assert client.post(BASE, json=body).status_code == 401
        denied = client.post(BASE, json=body, headers=headers)
        assert denied.status_code == 403, denied.text
        assert denied.json()["code"] == "PERMISSION_DENIED"

        db.expire_all()
        assert db.scalar(select(func.count(Bed.id))) == beds_before
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "PERMISSION_DENIED"))
            >= 1
        ), "越权尝试必须留痕"
    finally:
        db.close()


def test_admin_can_create_and_unknown_bed_is_404(client, admin_headers, ds):
    db = get_session_factory()()
    try:
        body = payload(db, ds, "WM-ADMIN-01", 10)
        assert client.post(BASE, json=body, headers=admin_headers).status_code == 201
        missing = client.post(
            f"{BASE}/99999999/archive",
            json={"confirm": True, "reason": "不存在"},
            headers=admin_headers,
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "NOT_FOUND"
    finally:
        db.close()
