"""床位分配服务：预占用 / 入住 / 出院 / 释放 / 取消。

并发安全
--------
* 业务层：``SELECT ... FOR UPDATE`` 对目标床位行加悲观锁，串行化同一床位的并发占用；
* 数据库层：``bed_allocations.active_bed_id`` 上的唯一索引作为兜底，
  即使锁失效也会由数据库拒绝第二条活动占用记录（IntegrityError -> 409）。

任一环节失败都会回滚整个事务，不会留下"半边状态"。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import (
    BizError,
    ConflictError,
    ErrorCode,
    NotFoundError,
    StateTransitionError,
)
from app.models.admission import AdmissionRequest
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.enums import (
    ADMISSION_REQUEST_STATUS_LABEL,
    ADMISSION_REQUEST_TRANSITIONS,
    ALLOCATION_STATUS_LABEL,
    ALLOCATION_TRANSITIONS,
    BED_STATUS_LABEL,
    BED_STATUS_TRANSITIONS,
    PRIORITY_LABEL,
    AdmissionRequestStatus,
    AllocationMode,
    AllocationStatus,
    AuditAction,
    AuditResult,
    BedStatus,
)
from app.models.facility import Bed
from app.models.user import User
from app.services import bed_policy
from app.services.audit import record_audit
from app.services.recommendation import recommend_beds


def _now() -> datetime:
    return datetime.now()


def _transition_bed(
    db: Session,
    bed: Bed,
    to_status: BedStatus,
    *,
    reason: str,
    operator: User | None,
    allocation_id: int | None = None,
    admission_request_id: int | None = None,
) -> None:
    """按状态机流转床位状态并写入流水。"""
    from_status = str(bed.status)
    allowed = BED_STATUS_TRANSITIONS.get(from_status, set())
    if to_status.value not in allowed:
        raise StateTransitionError(
            f"床位 {bed.code} 不允许从「{BED_STATUS_LABEL.get(from_status, from_status)}」"
            f"流转到「{BED_STATUS_LABEL.get(to_status.value, to_status.value)}」",
            detail={"bed_id": bed.id, "from": from_status, "to": to_status.value, "allowed": sorted(allowed)},
        )
    bed.status = to_status
    db.add(
        BedStatusLog(
            bed_id=bed.id,
            from_status=from_status,
            to_status=to_status.value,
            reason=reason,
            allocation_id=allocation_id,
            admission_request_id=admission_request_id,
            operator_id=getattr(operator, "id", None),
        )
    )


def assert_allocation_transition(alloc: BedAllocation, to_status: AllocationStatus) -> None:
    allowed = ALLOCATION_TRANSITIONS.get(str(alloc.status), set())
    if to_status.value not in allowed:
        raise StateTransitionError(
            f"分配记录 #{alloc.id} 不允许从「{ALLOCATION_STATUS_LABEL.get(str(alloc.status), str(alloc.status))}」"
            f"流转到「{ALLOCATION_STATUS_LABEL.get(to_status.value, to_status.value)}」",
            detail={
                "allocation_id": alloc.id,
                "from": str(alloc.status),
                "to": to_status.value,
                "allowed": sorted(allowed),
            },
        )


def assert_request_transition(request: AdmissionRequest, to_status: AdmissionRequestStatus) -> None:
    allowed = ADMISSION_REQUEST_TRANSITIONS.get(str(request.status), set())
    if to_status.value not in allowed:
        raise StateTransitionError(
            f"住院证 {request.certificate_no} 不允许从「"
            f"{ADMISSION_REQUEST_STATUS_LABEL.get(str(request.status), str(request.status))}」流转到「"
            f"{ADMISSION_REQUEST_STATUS_LABEL.get(to_status.value, to_status.value)}」",
            detail={
                "admission_request_id": request.id,
                "from": str(request.status),
                "to": to_status.value,
                "allowed": sorted(allowed),
            },
        )


def get_request(db: Session, request_id: int) -> AdmissionRequest:
    req = db.execute(
        select(AdmissionRequest)
        .options(
            joinedload(AdmissionRequest.patient),
            joinedload(AdmissionRequest.department),
            joinedload(AdmissionRequest.doctor),
            joinedload(AdmissionRequest.preadmission),
            joinedload(AdmissionRequest.preferred_ward),
        )
        .where(AdmissionRequest.id == request_id)
    ).unique().scalar_one_or_none()
    if req is None:
        raise NotFoundError(f"住院证 #{request_id} 不存在")
    return req


def get_bed(db: Session, bed_id: int) -> Bed:
    bed = db.execute(
        select(Bed).options(joinedload(Bed.ward), joinedload(Bed.department)).where(Bed.id == bed_id)
    ).unique().scalar_one_or_none()
    if bed is None:
        raise NotFoundError(f"床位 #{bed_id} 不存在")
    return bed


def reserve_bed(
    db: Session,
    *,
    request_id: int,
    bed_id: int | None,
    operator: User | None,
    confirm_top_recommendation: bool = False,
    note: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """预占用床位：硬约束校验 + 行级锁 + 事务提交。"""
    request = get_request(db, request_id)

    if str(request.status) not in {
        AdmissionRequestStatus.PRE_ADMITTED.value,
    }:
        raise StateTransitionError(
            f"住院证 {request.certificate_no} 当前状态为「"
            f"{ADMISSION_REQUEST_STATUS_LABEL.get(str(request.status), str(request.status))}」，"
            "只有完成预入院登记（待入院）的住院证才能分配床位",
            detail={"admission_request_id": request.id, "status": str(request.status)},
        )

    score: float | None = None
    score_detail: dict[str, Any] | None = None
    reason_text = note or ""

    if bed_id is None:
        # 采纳推荐：先做一次无锁的推荐计算
        rec = recommend_beds(db, request, limit=1)
        if not rec.recommendations:
            raise BizError(
                ErrorCode.NO_BED_AVAILABLE,
                "当前没有满足硬约束的可用床位，无法分配",
                409,
                detail={
                    "admission_request_id": request.id,
                    "reasons": rec.no_result_reasons,
                    "hard_constraint_stats": rec.hard_constraint_stats.model_dump(),
                },
            )
        top = rec.recommendations[0]
        bed_id = top.bed_id
        score = top.score
        score_detail = {
            "items": [item.model_dump() for item in top.score_items],
            "reasons": top.reasons,
            "warnings": top.warnings,
            "candidates_evaluated": rec.candidates_evaluated,
        }
        reason_text = reason_text or f"采纳推荐系统首选床位 {top.bed_code}（得分 {top.score}）"
        mode = AllocationMode.RECOMMENDED
    else:
        mode = (
            AllocationMode.RECOMMENDED if confirm_top_recommendation else AllocationMode.MANUAL
        )
        if confirm_top_recommendation:
            rec = recommend_beds(db, request, limit=50)
            matched = next((r for r in rec.recommendations if r.bed_id == bed_id), None)
            if matched is not None:
                score = matched.score
                score_detail = {
                    "items": [item.model_dump() for item in matched.score_items],
                    "reasons": matched.reasons,
                    "warnings": matched.warnings,
                    "candidates_evaluated": rec.candidates_evaluated,
                }
                reason_text = reason_text or f"确认采纳推荐床位 {matched.bed_code}（得分 {matched.score}）"
        if not reason_text:
            reason_text = "人工选择床位（已通过硬约束校验）"

    try:
        # 悲观锁：锁定目标床位行，直到本事务结束
        locked = db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            raise NotFoundError(f"床位 #{bed_id} 不存在")

        # 先判状态：已被占用属于「冲突」(409)，语义上比参数非法(422)更准确
        if str(locked.status) != BedStatus.AVAILABLE.value:
            raise ConflictError(
                ErrorCode.BED_NOT_AVAILABLE,
                f"床位 {locked.code} 当前状态为「"
                f"{BED_STATUS_LABEL.get(str(locked.status), str(locked.status))}」，已被占用",
                detail={"bed_id": locked.id, "bed_code": locked.code, "status": str(locked.status)},
            )

        # 再判其余硬约束（科室/性别/隔离）：属于「参数与约束不符」(422)
        violations = bed_policy.hard_constraint_violations(
            locked,
            department_id=request.department_id,
            patient_gender=str(request.patient.gender),
            isolation_required=bool(request.isolation_required),
        )
        if violations:
            raise BizError(
                ErrorCode.HARD_CONSTRAINT_VIOLATION,
                "选定床位不满足硬约束：" + "；".join(violations),
                422,
                detail={"bed_id": locked.id, "bed_code": locked.code, "violations": violations},
            )

        alloc = BedAllocation(
            admission_request_id=request.id,
            patient_id=request.patient_id,
            bed_id=locked.id,
            active_bed_id=locked.id,
            mode=mode,
            score=score,
            score_detail=score_detail,
            reason=reason_text,
            status=AllocationStatus.RESERVED,
            operator_id=getattr(operator, "id", None),
            reserved_at=_now(),
        )
        db.add(alloc)
        db.flush()  # 取得 alloc.id，同时触发 active_bed_id 唯一索引校验

        _transition_bed(
            db,
            locked,
            BedStatus.RESERVED,
            reason=f"预占用：住院证 {request.certificate_no}",
            operator=operator,
            allocation_id=alloc.id,
            admission_request_id=request.id,
        )

        # 该住院证不再参与待入院队列的其他占用
        pre = request.preadmission
        if pre is not None:
            pre.queue_sequence = pre.queue_sequence

        record_audit(
            db,
            action=AuditAction.RESERVE_BED.value,
            user=operator,
            object_type="bed_allocation",
            object_id=alloc.id,
            result=AuditResult.SUCCESS,
            detail={
                "admission_request_id": request.id,
                "certificate_no": request.certificate_no,
                "bed_id": locked.id,
                "bed_code": locked.code,
                "mode": mode.value,
                "score": score,
                "hard_constraint_checked": True,
            },
            ip=ip,
            user_agent=user_agent,
        )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            ErrorCode.BED_DOUBLE_BOOKED,
            "床位已被其他操作占用（数据库唯一约束拦截），请刷新后重试",
            detail={"bed_id": bed_id, "db_error": str(exc.orig)[:200]},
        ) from exc
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_allocation(db, alloc.id)


def get_allocation(db: Session, allocation_id: int) -> BedAllocation:
    alloc = db.execute(
        select(BedAllocation)
        .options(
            joinedload(BedAllocation.bed).joinedload(Bed.ward),
            joinedload(BedAllocation.patient),
            joinedload(BedAllocation.admission_request).joinedload(AdmissionRequest.department),
            joinedload(BedAllocation.operator),
        )
        .where(BedAllocation.id == allocation_id)
    ).unique().scalar_one_or_none()
    if alloc is None:
        raise NotFoundError(f"分配记录 #{allocation_id} 不存在")
    return alloc


def admit_patient(
    db: Session,
    *,
    allocation_id: int,
    operator: User | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """确认入住：预占用 -> 已入住。"""
    try:
        alloc = db.execute(
            select(BedAllocation).where(BedAllocation.id == allocation_id).with_for_update()
        ).scalar_one_or_none()
        if alloc is None:
            raise NotFoundError(f"分配记录 #{allocation_id} 不存在")

        assert_allocation_transition(alloc, AllocationStatus.ADMITTED)

        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()
        request = db.execute(
            select(AdmissionRequest).where(AdmissionRequest.id == alloc.admission_request_id)
        ).scalar_one()

        _transition_bed(
            db,
            bed,
            BedStatus.OCCUPIED,
            reason=f"办理入住：住院证 {request.certificate_no}",
            operator=operator,
            allocation_id=alloc.id,
            admission_request_id=request.id,
        )
        alloc.status = AllocationStatus.ADMITTED
        alloc.admitted_at = _now()

        assert_request_transition(request, AdmissionRequestStatus.ADMITTED)
        request.status = AdmissionRequestStatus.ADMITTED

        record_audit(
            db,
            action=AuditAction.ADMIT.value,
            user=operator,
            object_type="bed_allocation",
            object_id=alloc.id,
            detail={
                "bed_id": bed.id,
                "bed_code": bed.code,
                "admission_request_id": request.id,
                "certificate_no": request.certificate_no,
            },
            ip=ip,
            user_agent=user_agent,
        )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_allocation(db, allocation_id)


def discharge_patient(
    db: Session,
    *,
    allocation_id: int,
    operator: User | None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """办理出院：已入住 -> 已出院，床位进入清洁中。"""
    try:
        alloc = db.execute(
            select(BedAllocation).where(BedAllocation.id == allocation_id).with_for_update()
        ).scalar_one_or_none()
        if alloc is None:
            raise NotFoundError(f"分配记录 #{allocation_id} 不存在")

        assert_allocation_transition(alloc, AllocationStatus.DISCHARGED)

        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()
        request = db.execute(
            select(AdmissionRequest).where(AdmissionRequest.id == alloc.admission_request_id)
        ).scalar_one()

        _transition_bed(
            db,
            bed,
            BedStatus.CLEANING,
            reason=f"出院后清洁：住院证 {request.certificate_no}",
            operator=operator,
            allocation_id=alloc.id,
            admission_request_id=request.id,
        )
        alloc.status = AllocationStatus.DISCHARGED
        alloc.discharged_at = _now()
        alloc.active_bed_id = None  # 释放并发保护位，床位可再次被占用

        assert_request_transition(request, AdmissionRequestStatus.COMPLETED)
        request.status = AdmissionRequestStatus.COMPLETED

        record_audit(
            db,
            action=AuditAction.DISCHARGE.value,
            user=operator,
            object_type="bed_allocation",
            object_id=alloc.id,
            detail={
                "bed_id": bed.id,
                "bed_code": bed.code,
                "admission_request_id": request.id,
                "discharge_reason": reason,
            },
            ip=ip,
            user_agent=user_agent,
        )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_allocation(db, allocation_id)


def release_bed(
    db: Session,
    *,
    bed_id: int,
    operator: User | None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Bed:
    """床位释放：清洁中 -> 空闲（可再次分配）。"""
    try:
        bed = db.execute(select(Bed).where(Bed.id == bed_id).with_for_update()).scalar_one_or_none()
        if bed is None:
            raise NotFoundError(f"床位 #{bed_id} 不存在")

        alloc = db.execute(
            select(BedAllocation)
            .where(BedAllocation.bed_id == bed_id, BedAllocation.status == AllocationStatus.DISCHARGED)
            .order_by(BedAllocation.discharged_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        _transition_bed(
            db,
            bed,
            BedStatus.AVAILABLE,
            reason=reason or "清洁完成，床位释放",
            operator=operator,
            allocation_id=alloc.id if alloc else None,
            admission_request_id=alloc.admission_request_id if alloc else None,
        )
        if alloc is not None:
            alloc.released_at = _now()

        record_audit(
            db,
            action=AuditAction.RELEASE_BED.value,
            user=operator,
            object_type="bed",
            object_id=bed.id,
            detail={"bed_code": bed.code, "allocation_id": alloc.id if alloc else None},
            ip=ip,
            user_agent=user_agent,
        )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_bed(db, bed_id)


def cancel_allocation(
    db: Session,
    *,
    allocation_id: int,
    operator: User | None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """取消预占用：预占用 -> 已取消，床位回到空闲。"""
    try:
        alloc = db.execute(
            select(BedAllocation).where(BedAllocation.id == allocation_id).with_for_update()
        ).scalar_one_or_none()
        if alloc is None:
            raise NotFoundError(f"分配记录 #{allocation_id} 不存在")

        assert_allocation_transition(alloc, AllocationStatus.CANCELLED)
        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()

        _transition_bed(
            db,
            bed,
            BedStatus.AVAILABLE,
            reason=reason or "取消预占用，床位释放",
            operator=operator,
            allocation_id=alloc.id,
            admission_request_id=alloc.admission_request_id,
        )
        alloc.status = AllocationStatus.CANCELLED
        alloc.cancel_reason = reason
        alloc.active_bed_id = None

        record_audit(
            db,
            action=AuditAction.CANCEL_ALLOCATION.value,
            user=operator,
            object_type="bed_allocation",
            object_id=alloc.id,
            detail={"bed_id": bed.id, "bed_code": bed.code, "reason": reason},
            ip=ip,
            user_agent=user_agent,
        )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_allocation(db, allocation_id)


def priority_summary_text(request: AdmissionRequest) -> str:
    return PRIORITY_LABEL.get(str(request.priority), str(request.priority))
