"""智能床位推荐测试：普通推荐、隔离不匹配、性别冲突、无空床、高优先级适配。"""

from __future__ import annotations

from tests.conftest import make_request, set_bed_status


def rec(client, headers, request_id: int, **params):
    resp = client.get(
        f"/api/v1/admission-requests/{request_id}/bed-recommendations", headers=headers, params=params
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_normal_patient_recommendation(client, ds, doctor_headers):
    """普通患者：硬约束过滤后返回可解释的排序结果。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", seq=1)
    data = rec(client, doctor_headers, req_id)

    stats = data["hard_constraint_stats"]
    assert stats["department_total_beds"] == 8
    assert stats["department_available_beds"] == 8
    assert stats["excluded_by_status"] == 0
    assert stats["excluded_by_gender"] == 1, "C-W1-03 为女床，男患者应被排除"
    assert stats["excluded_by_isolation"] == 0

    assert data["candidates_evaluated"] == 7
    assert len(data["recommendations"]) == 7
    assert data["no_result_reasons"] == []

    scores = [r["score"] for r in data["recommendations"]]
    assert scores == sorted(scores, reverse=True), "结果必须按总分倒序"
    assert len(set(scores)) > 1, "不同床位必须得到不同分数（否则评分退化）"

    top = data["recommendations"][0]
    assert len(top["score_items"]) == 5, "五个评分项都应返回"
    assert abs(sum(i["weight"] for i in top["score_items"]) - 1.0) < 1e-6, "权重合计应为 1.0"
    assert top["reasons"], "必须给出推荐理由"
    assert "隔离床的策略" not in top["reasons"][0]
    assert any("硬约束全部通过" in r for r in top["reasons"])

    # 每个候选都带有中文评分解释
    for item in top["score_items"]:
        assert item["label"] and item["note"]
        assert 0 <= item["raw_score"] <= 100

    assert data["policy_notes"], "应返回隔离床策略说明"


def test_isolation_required_but_no_isolation_bed(client, ds, doctor_headers):
    """隔离要求不匹配：科室没有隔离床时返回明确原因，且不降级到普通床。"""
    req_id = make_request(
        ds, patient_name="男患者甲", department_code="CARD", isolation_required=True, seq=2
    )
    data = rec(client, doctor_headers, req_id)

    assert data["recommendations"] == []
    stats = data["hard_constraint_stats"]
    assert stats["department_available_beds"] == 8
    assert stats["excluded_by_isolation"] == 8, "8 张空闲床全部因非隔离床被排除"

    reasons = " ".join(data["no_result_reasons"])
    assert "隔离" in reasons
    assert "P5" in reasons or "不降级" in reasons


def test_isolation_bed_not_open_to_normal_patient(client, ds, doctor_headers):
    """隔离要求不匹配（反向）：隔离床不向非隔离患者开放。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="INF", seq=3)
    data = rec(client, doctor_headers, req_id)

    assert data["recommendations"] == []
    assert data["hard_constraint_stats"]["excluded_by_isolation"] == 3
    reasons = " ".join(data["no_result_reasons"])
    assert "隔离床" in reasons and ("P2" in reasons or "只对隔离患者开放" in reasons)


def test_gender_conflict(client, ds, doctor_headers):
    """性别冲突：骨科只有女床，男患者无候选并返回 H3 原因。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="ORTH", seq=4)
    data = rec(client, doctor_headers, req_id)

    assert data["recommendations"] == []
    assert data["hard_constraint_stats"]["excluded_by_gender"] == 3
    reasons = " ".join(data["no_result_reasons"])
    assert "性别" in reasons and "H3" in reasons


def test_gender_match_succeeds_for_female_patient(client, ds, doctor_headers):
    """对照组：女患者在骨科（女病房）可以正常获得推荐。"""
    req_id = make_request(ds, patient_name="女患者乙", department_code="ORTH", seq=5)
    data = rec(client, doctor_headers, req_id)
    assert len(data["recommendations"]) == 3
    assert data["hard_constraint_stats"]["excluded_by_gender"] == 0


def test_no_available_bed(client, ds, doctor_headers):
    """无空床：全部床位被占用时返回明确原因。"""
    for code in ("P-W1-01", "P-W1-02"):
        set_bed_status(ds.bed(code), "OCCUPIED")

    req_id = make_request(ds, patient_name="男童丁", department_code="PED", seq=6)
    data = rec(client, doctor_headers, req_id)

    assert data["recommendations"] == []
    stats = data["hard_constraint_stats"]
    assert stats["department_total_beds"] == 2
    assert stats["department_available_beds"] == 0
    assert stats["excluded_by_status"] == 2
    reasons = " ".join(data["no_result_reasons"])
    assert "没有任何空闲床位" in reasons
    assert "已入住 2 张" in reasons


def test_high_priority_prefers_monitor_bed(client, ds, doctor_headers):
    """高优先级适配：危重患者应优先监护床（靠近护士站）。"""
    req_id = make_request(
        ds, patient_name="男患者甲", department_code="CARD", priority="CRITICAL", seq=7
    )
    data = rec(client, doctor_headers, req_id)
    top = data["recommendations"][0]
    assert top["bed_type"] == "MONITOR", f"危重患者首选应为监护床，实际 {top['bed_code']}"
    assert top["bed_code"].startswith("C-ICU")
    fit = next(i for i in top["score_items"] if i["key"] == "priority_fit")
    assert fit["raw_score"] >= 100 - 9  # 100 基础 + 1 层加分（封顶 100）


def test_low_priority_avoids_monitor_bed(client, ds, doctor_headers):
    """低优先级适配：轻症患者不应占用监护床、并优先远离护士站的普通床。"""
    req_id = make_request(ds, patient_name="男患者甲", department_code="CARD", priority="MILD", seq=8)
    data = rec(client, doctor_headers, req_id)
    top = data["recommendations"][0]
    assert top["bed_type"] == "NORMAL", f"轻症患者首选应为普通床，实际 {top['bed_code']}"

    monitor_scores = [r["score"] for r in data["recommendations"] if r["bed_type"] == "MONITOR"]
    normal_scores = [r["score"] for r in data["recommendations"] if r["bed_type"] == "NORMAL"]
    assert min(normal_scores) > max(monitor_scores), "轻症患者下监护床应整体排后"


def test_priority_is_not_a_constant_score(client, ds, doctor_headers):
    """同一张床位对不同优先级患者必须得到不同分数（优先级不是常数）。"""
    critical_id = make_request(
        ds, patient_name="男患者甲", department_code="CARD", priority="CRITICAL", seq=9
    )
    mild_id = make_request(
        ds, patient_name="男患者丙", department_code="CARD", priority="MILD", seq=10
    )

    crit = {r["bed_id"]: r["score"] for r in rec(client, doctor_headers, critical_id)["recommendations"]}
    mild = {r["bed_id"]: r["score"] for r in rec(client, doctor_headers, mild_id)["recommendations"]}

    common = set(crit) & set(mild)
    assert common, "两次推荐应存在共同候选床位"
    assert any(crit[bed] != mild[bed] for bed in common), "同一床位对不同优先级得分必须不同"

    # 排序差异：危重首选监护床，轻症首选普通床
    crit_top = max(crit.items(), key=lambda kv: kv[1])[0]
    mild_top = max(mild.items(), key=lambda kv: kv[1])[0]
    assert crit_top != mild_top, "不同优先级患者的推荐首位应不同"
