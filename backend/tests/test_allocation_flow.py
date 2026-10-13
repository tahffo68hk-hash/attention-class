"""床位分配流程测试：人工调整、科室冲突、非法状态流转、完整出入院闭环。"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.facility import Bed
from tests.conftest import make_request


def bed_status(bed_id: int) -> str:
    db = get_session_factory()()
    try:
        return str(db.get(Bed, bed_id).status)
    finally:
        db.close()


def allocation_status(allocation_id: int) -> str:
    db = get_session_factory()()
    try:
        return str(db.get(BedAllocation, allocation_id).status)
    finally:
        db.close()


def status_logs(bed_id: int) -> list[tuple[str, str]]:
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(BedStatusLog)
            .where(BedStatusLog.bed_id == bed_id)
            .order_by(BedStatusLog.id.asc())
        ).scalars()
        return [(str(r.from_status) if r.from_status else "-", str(r.to_status)) for r in rows]
    finally:
        db.close()


def reserve(client, headers, request_id: int, **payload):
    body = {"admission_request_id": request_id, **payload}
    return client.post("/api/v1/allocations", json=body, headers=headers)


# --------------------------------------------------------------------------- #
# 人工调整
# --------------------------------------------------------------------------- #
def test_manual_selection_is_allowed_and_marked(client, ds, nurse_headers):
    """人工选择床位：通过硬约束校验后成功，模式标记为人工选择。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=1)
    target = ds.bed("C-W1-01")

    resp = reserve(client, nurse_headers, req_id, bed_id=target, note="护士人工挑选靠近窗户的床位")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "MANUAL"
    assert body["status"] == "RESERVED"
    assert body["bed_code"] == "C-W1-01"
    assert body["score"] is None, "人工选择不应伪造推荐得分"
    assert bed_status(target) == "RESERVED"


def test_confirm_top_recommendation_is_marked_recommended(client, ds, nurse_headers):
    """采纳推荐首位：模式标记为推荐确认，并保留得分明细。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=2)
    data = client.get(
        f"/api/v1/admission-requests/{req_id}/bed-recommendations", headers=nurse_headers
    ).json()
    top = data["recommendations"][0]

    resp = reserve(client, nurse_headers, req_id, bed_id=top["bed_id"], confirm_top_recommendation=True)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "RECOMMENDED"
    assert float(body["score"]) == top["score"]


def test_reserve_without_bed_id_adopts_top_recommendation(client, ds, nurse_headers):
    """不指定床位时自动采纳推荐第一名。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=3)
    resp = reserve(client, nurse_headers, req_id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["mode"] == "RECOMMENDED"
    assert resp.json()["reason"].startswith("采纳推荐系统首选床位")


# --------------------------------------------------------------------------- #
# 科室冲突（人工选择也必须遵守硬约束）
# --------------------------------------------------------------------------- #
def test_manual_selection_cross_department_rejected(client, ds, nurse_headers):
    """科室冲突：人工选择跨科室床位必须被拒绝。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=4)
    other_dept_bed = ds.bed("O-W1-01")  # 骨科女床，既跨科室又性别冲突

    resp = reserve(client, nurse_headers, req_id, bed_id=other_dept_bed)
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "HARD_CONSTRAINT_VIOLATION"
    violations = " ".join(body["detail"]["violations"])
    assert "H2" in violations, "应报告科室不匹配"
    assert bed_status(other_dept_bed) == "AVAILABLE", "失败后床位状态不得改变"


def test_manual_selection_isolation_mismatch_rejected(client, ds, nurse_headers):
    """隔离需求不匹配：非隔离患者人工选择隔离床被拒绝。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="INF", seq=5)
    iso_bed = ds.bed("I-W1-01")

    resp = reserve(client, nurse_headers, req_id, bed_id=iso_bed)
    assert resp.status_code == 422, resp.text
    assert "P2" in " ".join(resp.json()["detail"]["violations"])


def test_manual_selection_gender_conflict_rejected(client, ds, nurse_headers):
    """性别冲突：男患者人工选择女床被拒绝。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=6)
    resp = reserve(client, nurse_headers, req_id, bed_id=ds.bed("C-W1-03"))
    assert resp.status_code == 422, resp.text
    assert "H3" in " ".join(resp.json()["detail"]["violations"])


# --------------------------------------------------------------------------- #
# 非法状态流转
# --------------------------------------------------------------------------- #
def test_cannot_allocate_before_preadmission(client, ds, nurse_headers):
    """非法状态流转：仅已开具（未预入院）的住院证不能分配床位。"""
    req_id = make_request(
        ds, patient_name="男患者甲", department_code="CARD", status="ISSUED", with_preadmission=False, seq=7
    )
    resp = reserve(client, nurse_headers, req_id)
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "ILLEGAL_STATE_TRANSITION"
    assert "预入院" in body["message"]


def test_cannot_double_admit(client, ds, nurse_headers):
    """非法状态流转：已入住的分配记录不能再次入住。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=8)
    alloc_id = reserve(client, nurse_headers, req_id).json()["id"]

    first = client.post(f"/api/v1/allocations/{alloc_id}/admit", headers=nurse_headers)
    assert first.status_code == 200, first.text

    second = client.post(f"/api/v1/allocations/{alloc_id}/admit", headers=nurse_headers)
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "ILLEGAL_STATE_TRANSITION"


def test_cannot_cancel_after_admit(client, ds, nurse_headers):
    """非法状态流转：已入住后不能取消预占用。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=9)
    alloc_id = reserve(client, nurse_headers, req_id).json()["id"]
    client.post(f"/api/v1/allocations/{alloc_id}/admit", headers=nurse_headers)

    resp = client.post(
        f"/api/v1/allocations/{alloc_id}/cancel", json={"reason": "测试"}, headers=nurse_headers
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "ILLEGAL_STATE_TRANSITION"


def test_cannot_release_available_bed(client, ds, nurse_headers):
    """非法状态流转：空闲床位不能执行「释放」。"""
    resp = client.post(f"/api/v1/beds/{ds.bed('C-W1-01')}/release", headers=nurse_headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "ILLEGAL_STATE_TRANSITION"


def test_cannot_allocate_occupied_bed(client, ds, nurse_headers):
    """床位不可用：已被占用的床位的分配请求返回 409。"""
    req_a = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=10)
    req_b = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=11)
    bed = ds.bed("C-W1-01")

    assert reserve(client, nurse_headers, req_a, bed_id=bed).status_code == 201
    resp = reserve(client, nurse_headers, req_b, bed_id=bed)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "BED_NOT_AVAILABLE"


# --------------------------------------------------------------------------- #
# 完整业务闭环
# --------------------------------------------------------------------------- #
def test_full_flow_reserve_admit_discharge_release(client, ds, nurse_headers):
    """预占用 -> 入住 -> 出院 -> 释放，全流程状态与流水正确。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=12)
    bed = ds.bed("C-W1-02")

    alloc_id = reserve(client, nurse_headers, req_id, bed_id=bed).json()["id"]
    assert bed_status(bed) == "RESERVED"

    r = client.post(f"/api/v1/allocations/{alloc_id}/admit", headers=nurse_headers)
    assert r.status_code == 200, r.text
    assert bed_status(bed) == "OCCUPIED"
    assert allocation_status(alloc_id) == "ADMITTED"

    # 住院证状态同步为已入住
    req_detail = client.get(f"/api/v1/admission-requests/{req_id}", headers=nurse_headers).json()
    assert req_detail["status"] == "ADMITTED"

    r = client.post(
        f"/api/v1/allocations/{alloc_id}/discharge", json={"reason": "治疗结束"}, headers=nurse_headers
    )
    assert r.status_code == 200, r.text
    assert bed_status(bed) == "CLEANING"
    assert allocation_status(alloc_id) == "DISCHARGED"

    req_detail = client.get(f"/api/v1/admission-requests/{req_id}", headers=nurse_headers).json()
    assert req_detail["status"] == "COMPLETED"

    r = client.post(f"/api/v1/beds/{bed}/release", headers=nurse_headers)
    assert r.status_code == 200, r.text
    assert bed_status(bed) == "AVAILABLE"

    # 每次状态变化都留痕
    logs = status_logs(bed)
    assert logs == [
        ("AVAILABLE", "RESERVED"),
        ("RESERVED", "OCCUPIED"),
        ("OCCUPIED", "CLEANING"),
        ("CLEANING", "AVAILABLE"),
    ]

    # 释放后床位可再次分配
    req2 = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=13)
    assert reserve(client, nurse_headers, req2, bed_id=bed).status_code == 201


def test_cancel_returns_bed_to_available(client, ds, nurse_headers):
    """取消预占用后床位回到空闲，并可被其它住院证占用。"""
    req_a = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=14)
    req_b = make_request(ds, patient_name="男患者丙", department_code="CARD", seq=15)
    bed = ds.bed("C-W2-01")

    alloc_id = reserve(client, nurse_headers, req_a, bed_id=bed).json()["id"]
    assert bed_status(bed) == "RESERVED"

    r = client.post(
        f"/api/v1/allocations/{alloc_id}/cancel", json={"reason": "患者暂缓入院"}, headers=nurse_headers
    )
    assert r.status_code == 200, r.text
    assert bed_status(bed) == "AVAILABLE"
    assert reserve(client, nurse_headers, req_b, bed_id=bed).status_code == 201
