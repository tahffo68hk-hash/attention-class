"""P1 只读优化快照适配；使用已有 H1–H4 与五维评分，绝不重新发明评分。"""
from __future__ import annotations
from datetime import datetime, timezone
from dataclasses import asdict
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BizError, ErrorCode, NotFoundError
from app.models.admission import AdmissionRequest
from app.models.allocation import BedAllocation
from app.models.enums import AdmissionRequestStatus, AllocationStatus, PRIORITY_RANK
from app.schemas.optimization import OptimizationPreviewOut, OptimizationResultOut
from app.services.global_optimization import EdgeCandidate, compare, optimize, greedy
from app.services.recommendation import recommend_beds


def preview(db: Session, request_ids: list[int], *, solver: str = "auto") -> OptimizationPreviewOut:
    if not request_ids or len(request_ids) > 30 or len(set(request_ids)) != len(request_ids) or any(
        not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in request_ids
    ):
        raise BizError(ErrorCode.VALIDATION_ERROR, "请输入 1–30 个不重复的有效住院证 ID", 422)
    rows = list(db.execute(select(AdmissionRequest).options(
        joinedload(AdmissionRequest.patient), joinedload(AdmissionRequest.department),
        joinedload(AdmissionRequest.preadmission), joinedload(AdmissionRequest.preferred_ward),
    ).where(AdmissionRequest.id.in_(request_ids))).unique().scalars())
    if len(rows) != len(request_ids):
        raise NotFoundError("有住院证不存在")
    active = set(db.scalars(select(BedAllocation.admission_request_id).where(
        BedAllocation.admission_request_id.in_(request_ids),
        BedAllocation.status.in_([AllocationStatus.RESERVED, AllocationStatus.ADMITTED]),
    )).all())
    edges: list[EdgeCandidate] = []
    for row in sorted(rows, key=lambda x: x.id):
        if row.status != AdmissionRequestStatus.PRE_ADMITTED or row.preadmission is None or row.id in active:
            raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION,
                           f"住院证 #{row.id} 不处于未分配的待入院状态", 409)
        recommended = recommend_beds(db, row, limit=None)
        if len(recommended.recommendations) > 100:
            raise BizError(ErrorCode.VALIDATION_ERROR, "单患者超过 100 个候选床位，请按科室缩小规模", 422)
        for bed in recommended.recommendations:
            edges.append(EdgeCandidate(row.id, bed.bed_id, PRIORITY_RANK[str(row.priority)], bed.score))
    if len(edges) > 2000:
        raise BizError(ErrorCode.VALIDATION_ERROR, "本批次候选关系超过 2000，请分批处理", 422)
    try:
        base = greedy(edges, request_ids)
        best = optimize(edges, request_ids, backend=solver)
    except (ValueError, RuntimeError) as exc:
        raise BizError(ErrorCode.VALIDATION_ERROR, str(exc), 422) from exc
    def out(solution):
        data = asdict(solution)
        data["pairs"] = [{"admission_request_id": p["request_id"], "bed_id": p["bed_id"],
                          "priority_rank": p["priority_rank"], "score": p["score"]}
                         for p in data["pairs"]]
        return OptimizationResultOut.model_validate(data)

    return OptimizationPreviewOut(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        admission_request_ids=sorted(request_ids),
        request_count=len(request_ids), candidate_edges=len(edges),
        baseline=out(base),
        optimized=out(best),
        admitted_gain=best.admitted-base.admitted,
        score_gain=round(best.score_sum-base.score_sum,2),
    )
