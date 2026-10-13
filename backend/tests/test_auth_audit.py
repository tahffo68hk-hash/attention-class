"""认证、角色权限、脱敏与审计留痕测试。"""

from __future__ import annotations

from tests.conftest import make_request


def audit_entries(client, admin_headers, **filters):
    resp = client.get("/api/v1/audit-logs", headers=admin_headers, params={**filters, "page_size": 100})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
def test_login_success_and_me(client, ds):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "ADMIN"
    assert body["user"]["role_label"] == "系统管理员"

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_login_failed_is_audited(client, admin_headers):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    entries = audit_entries(client, admin_headers, action="LOGIN_FAILED")
    assert entries, "登录失败必须留痕"
    assert entries[0]["result"] == "FAILURE"
    assert entries[0]["detail"]["username"] == "admin"


def test_missing_token_returns_unified_401(client):
    resp = client.get("/api/v1/beds")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_TOKEN_INVALID"
    assert set(body) == {"code", "message", "detail", "request_id"}


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/beds", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_TOKEN_INVALID"


# --------------------------------------------------------------------------- #
# 越权操作 + 审计留痕
# --------------------------------------------------------------------------- #
def test_viewer_cannot_create_admission_request(client, ds, viewer_headers, admin_headers):
    """越权操作：只读用户开具住院证被拒绝，并留下失败审计。"""
    resp = client.post(
        "/api/v1/admission-requests",
        json={
            "patient_id": ds.patients["男患者甲"],
            "department_id": ds.departments["CARD"],
            "priority": "NORMAL",
        },
        headers=viewer_headers,
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "PERMISSION_DENIED"
    assert "VIEWER" in body["message"]

    entries = audit_entries(client, admin_headers, action="PERMISSION_DENIED", username="viewer01")
    assert entries, "越权操作必须留痕"
    top = entries[0]
    assert top["result"] == "FAILURE"
    assert top["role"] == "VIEWER"
    assert top["detail"]["required_roles"] == ["ADMIN", "DOCTOR"]
    assert top["detail"]["path"] == "/api/v1/admission-requests"


def test_doctor_cannot_allocate_bed(client, ds, doctor_headers):
    """越权操作：医生不能执行床位分配（由护士/管理员完成）。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=1)
    resp = client.post(
        "/api/v1/allocations", json={"admission_request_id": req_id}, headers=doctor_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"


def test_non_admin_cannot_read_audit_logs(client, viewer_headers, nurse_headers, doctor_headers):
    for headers in (viewer_headers, nurse_headers, doctor_headers):
        resp = client.get("/api/v1/audit-logs", headers=headers)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "PERMISSION_DENIED"


def test_nurse_cannot_manage_base_data(client, ds, nurse_headers):
    resp = client.post(
        "/api/v1/departments",
        json={"code": "NEW", "name": "新科室"},
        headers=nurse_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"


# --------------------------------------------------------------------------- #
# 敏感信息脱敏
# --------------------------------------------------------------------------- #
def test_patient_list_masked_by_default(client, ds, nurse_headers, admin_headers):
    resp = client.get("/api/v1/patients", headers=nurse_headers)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["masked"] is True
    assert "*" in item["name"]
    assert "*" in item["phone"]
    assert "*" in item["id_card"]


def test_reveal_requires_admin(client, ds, nurse_headers, admin_headers):
    resp = client.get("/api/v1/patients", params={"reveal": "true"}, headers=nurse_headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"

    entries = audit_entries(client, admin_headers, action="REVEAL_SENSITIVE", result="FAILURE")
    assert entries, "越权查看明文必须留痕"

    ok = client.get("/api/v1/patients", params={"reveal": "true"}, headers=admin_headers)
    assert ok.status_code == 200
    item = ok.json()["items"][0]
    assert item["masked"] is False
    assert "*" not in item["name"]

    success = audit_entries(client, admin_headers, action="REVEAL_SENSITIVE", result="SUCCESS")
    assert success, "管理员查看明文同样必须留痕"


# --------------------------------------------------------------------------- #
# 关键操作审计
# --------------------------------------------------------------------------- #
def test_key_operations_are_audited(client, ds, doctor_headers, nurse_headers, admin_headers):
    """开具住院证 / 预入院 / 推荐 / 分配 / 入住 都应有审计记录。"""
    create = client.post(
        "/api/v1/admission-requests",
        json={
            "patient_id": ds.patients["男患者甲"],
            "department_id": ds.departments["CARD"],
            "priority": "SEVERE",
            "isolation_required": False,
        },
        headers=doctor_headers,
    )
    assert create.status_code == 201, create.text
    req_id = create.json()["id"]

    pre = client.post(
        f"/api/v1/admission-requests/{req_id}/preadmission",
        json={"deposit_amount": "3000.00", "pay_deposit": True, "contact_phone": "13800000000"},
        headers=nurse_headers,
    )
    assert pre.status_code == 201, pre.text
    assert pre.json()["deposit_status"] == "PAID"

    assert (
        client.get(
            f"/api/v1/admission-requests/{req_id}/bed-recommendations", headers=nurse_headers
        ).status_code
        == 200
    )

    alloc = client.post(
        "/api/v1/allocations", json={"admission_request_id": req_id}, headers=nurse_headers
    )
    assert alloc.status_code == 201, alloc.text
    alloc_id = alloc.json()["id"]

    assert client.post(f"/api/v1/allocations/{alloc_id}/admit", headers=nurse_headers).status_code == 200

    actions = {e["action"] for e in audit_entries(client, admin_headers)}
    for expected in ("ISSUE_CERTIFICATE", "PRE_ADMISSION", "RECOMMEND"):
        assert expected in actions, f"缺少 {expected} 审计记录"

    alloc_actions = {
        e["action"] for e in audit_entries(client, admin_headers, object_type="bed_allocation")
    }
    for expected in ("RESERVE_BED", "ADMIT"):
        assert expected in alloc_actions, f"缺少 {expected} 审计记录"

    # 预入院审计记录应记录模拟支付方式
    pre_entry = next(e for e in audit_entries(client, admin_headers, action="PRE_ADMISSION"))
    assert "模拟" in pre_entry["detail"]["payment_mode"]

    entry = audit_entries(client, admin_headers, action="RESERVE_BED")[0]
    assert entry["username"] == "nurse01"
    assert entry["result"] == "SUCCESS"
    assert entry["detail"]["hard_constraint_checked"] is True
    assert entry["created_at"] is not None


# --------------------------------------------------------------------------- #
# 看板
# --------------------------------------------------------------------------- #
def test_dashboard_summary(client, ds, nurse_headers):
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=9)
    assert (
        client.post(
            "/api/v1/allocations", json={"admission_request_id": req_id}, headers=nurse_headers
        ).status_code
        == 201
    )

    resp = client.get("/api/v1/dashboard/summary", headers=nurse_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_beds"] == 16
    assert data["reserved_beds"] == 1
    assert data["available_beds"] == 15
    assert data["occupied_beds"] == 0
    assert data["pending_admission_patients"] >= 1
    assert data["isolation_beds_total"] == 3
    assert data["isolation_beds_available"] == 3
    assert len(data["department_stats"]) == 4
    assert {p["priority"] for p in data["pending_queue_by_priority"]} == {
        "CRITICAL",
        "SEVERE",
        "URGENT",
        "NORMAL",
        "MILD",
    }
