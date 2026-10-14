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
import hashlib
import json

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
from app.models.allocation import BedAllocation, BedStatusLog, AllocationIdempotency
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
            reason=reason[:255],
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



def _fingerprint_reservation(request_id: int, bed_id: int | None, confirm: bool, note: str | None) -> str:
    """Hash all behavior-affecting arguments; same key + different body must be rejected."""
    canonical = json.dumps(
        {"request_id": request_id, "bed_id": bed_id,
         "confirm_top_recommendation": confirm, "note": note},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replay_idempotency(db: Session, key: str, digest: str) -> BedAllocation:
    record = db.execute(
        select(AllocationIdempotency).where(AllocationIdempotency.request_key == key)
    ).scalar_one_or_none()
    if record is None:
        raise ConflictError(ErrorCode.DUPLICATE_RESOURCE, "幂等写入冲突，请重试")
    if record.payload_sha256 != digest:
        raise ConflictError(
            ErrorCode.IDEMPOTENCY_KEY_CONFLICT,
            "相同 Idempotency-Key 已用于不同请求参数",
        )
    if record.allocation_id is None:
        raise ConflictError(ErrorCode.DUPLICATE_RESOURCE, "首次操作尚未完成，请稍后重试")
    return get_allocation(db, record.allocation_id)


def _reserve_idempotency(db: Session, key: str, digest: str) -> tuple[AllocationIdempotency | None, BedAllocation | None]:
    if not 8 <= len(key) <= 128 or not key.isascii() or any(ord(x) < 33 or ord(x) > 126 for x in key):
        raise BizError(ErrorCode.VALIDATION_ERROR, "无效 Idempotency-Key", 422)
    # A fast replay path and a unique-insert race gate. InnoDB unique-index
    # insertion blocks the second in-flight writer until the first commits.
    previous = db.execute(
        select(AllocationIdempotency).where(AllocationIdempotency.request_key == key)
    ).scalar_one_or_none()
    if previous is not None:
        return None, _replay_idempotency(db, key, digest)
    record = AllocationIdempotency(request_key=key, payload_sha256=digest)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # A competing identical request may have committed during the insert.
        return None, _replay_idempotency(db, key, digest)
    return record, None


def _lock_request(db: Session, request_id: int) -> AdmissionRequest:
    """Common lock first: admission request -> allocation -> bed(s)."""
    row = db.execute(
        select(AdmissionRequest).where(AdmissionRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"住院证 #{request_id} 不存在")
    return get_request(db, request_id)


def _assert_pair(alloc: BedAllocation, bed: Bed, *, status: AllocationStatus, bed_status: BedStatus) -> None:
    if str(alloc.status) != status.value or str(bed.status) != bed_status.value or alloc.active_bed_id != bed.id:
        raise ConflictError(
            ErrorCode.ILLEGAL_STATE_TRANSITION,
            "床位状态与活动分配记录不一致，拒绝修改",
            detail={"allocation_id": alloc.id, "bed_id": bed.id,
                    "allocation_status": str(alloc.status), "bed_status": str(bed.status)},
        )


def _lock_alloc_and_request(db: Session, allocation_id: int) -> tuple[AdmissionRequest, BedAllocation]:
    request_id = db.execute(
        select(BedAllocation.admission_request_id).where(BedAllocation.id == allocation_id)
    ).scalar_one_or_none()
    if request_id is None:
        raise NotFoundError(f"分配记录 #{allocation_id} 不存在")
    request = _lock_request(db, request_id)
    alloc = db.execute(
        select(BedAllocation).where(BedAllocation.id == allocation_id).with_for_update()
    ).scalar_one_or_none()
    if alloc is None or alloc.admission_request_id != request.id:
        raise NotFoundError(f"分配记录 #{allocation_id} 不存在")
    return request, alloc

def reserve_bed(
    db: Session,
    *,
    request_id: int,
    bed_id: int | None,
    operator: User | None,
    confirm_top_recommendation: bool = False,
    note: str | None = None,
    idempotency_key: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """预占：先获取幂等键，再锁住院证、锁床位，双唯一约束兜底。"""
    idem_record: AllocationIdempotency | None = None
    digest = _fingerprint_reservation(request_id, bed_id, confirm_top_recommendation, note)
    try:
        if idempotency_key is not None:
            idem_record, replayed = _reserve_idempotency(db, idempotency_key, digest)
            if replayed is not None:
                return replayed
        request = _lock_request(db, request_id)
        # A different key or no key must not allocate another bed to this request.
        active = db.execute(
            select(BedAllocation.id).where(
                BedAllocation.admission_request_id == request_id,
                BedAllocation.status.in_([AllocationStatus.RESERVED, AllocationStatus.ADMITTED]),
            ).limit(1)
        ).scalar_one_or_none()
        if active is not None:
            raise ConflictError(
                ErrorCode.REQUEST_ALREADY_ALLOCATED,
                "同一住院证已有活动分配，不能再占用其他床位",
                detail={"admission_request_id": request_id, "allocation_id": active},
            )
    except Exception:
        db.rollback()
        raise

    try:
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
        db.flush()  # triggers both unique constraints; alloc.id available
        if idem_record is not None:
            idem_record.allocation_id = alloc.id

        _transition_bed(
            db,
            locked,
            BedStatus.RESERVED,
            reason=f"预占用：住院证 {request.certificate_no}",
            operator=operator,
            allocation_id=alloc.id,
            admission_request_id=request.id,
        )

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
            "床位或住院证已有活动占用（数据库唯一约束拦截），请刷新后重试",
            detail={"bed_id": bed_id, "admission_request_id": request_id},
        ) from exc
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return get_allocation(db, alloc.id)



def reassign_reserved_bed(
    db: Session,
    *,
    allocation_id: int,
    new_bed_id: int,
    reason: str,
    operator: User | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BedAllocation:
    """Atomically swap a RESERVED bed for another eligible AVAILABLE bed.

    Lock order: request -> old allocation -> beds sorted by id. All writes
    (old allocation cancellation, both bed states, new allocation and audit)
    are committed together; uniqueness is maintained between FLUSH steps.
    """
    try:
        request, old = _lock_alloc_and_request(db, allocation_id)
        if str(old.status) != AllocationStatus.RESERVED.value:
            raise StateTransitionError("仅预占用状态支持人工换床")
        if str(request.status) != AdmissionRequestStatus.PRE_ADMITTED.value:
            raise StateTransitionError("住院证状态不允许换床")
        if new_bed_id == old.bed_id:
            raise ConflictError(ErrorCode.DUPLICATE_RESOURCE, "新旧床位不能相同")

        beds: dict[int, Bed] = {}
        for identifier in sorted([old.bed_id, new_bed_id]):
            bed = db.execute(
                select(Bed).where(Bed.id == identifier).with_for_update()
            ).scalar_one_or_none()
            if bed is None:
                raise NotFoundError(f"床位 #{identifier} 不存在")
            beds[identifier] = bed
        source, target = beds[old.bed_id], beds[new_bed_id]
        _assert_pair(old, source, status=AllocationStatus.RESERVED, bed_status=BedStatus.RESERVED)
        if str(target.status) != BedStatus.AVAILABLE.value:
            raise ConflictError(ErrorCode.BED_NOT_AVAILABLE, "目标床位已被占用或不可用")
        violations = bed_policy.hard_constraint_violations(
            target, department_id=request.department_id,
            patient_gender=str(request.patient.gender),
            isolation_required=bool(request.isolation_required),
        )
        if violations:
            raise BizError(ErrorCode.HARD_CONSTRAINT_VIOLATION,
                           "目标床位不满足硬约束：" + "；".join(violations),
                           422, detail={"violations": violations})

        # First release the old assignment: the generated unique active_request_id
        # is freed upon flush, then the new one may be inserted in this transaction.
        old.status = AllocationStatus.CANCELLED
        old.active_bed_id = None
        old.cancel_reason = f"换床至 {target.code}：{reason}"[:255]
        _transition_bed(db, source, BedStatus.AVAILABLE,
                        reason=f"人工换床释放原床：{reason}", operator=operator,
                        allocation_id=old.id, admission_request_id=request.id)
        db.flush()

        new = BedAllocation(
            admission_request_id=request.id, patient_id=request.patient_id,
            bed_id=target.id, active_bed_id=target.id,
            mode=AllocationMode.MANUAL, status=AllocationStatus.RESERVED,
            operator_id=getattr(operator, "id", None),
            reserved_at=_now(), reason=f"由床位 {source.code} 人工调整：{reason}",
        )
        db.add(new)
        db.flush()
        _transition_bed(db, target, BedStatus.RESERVED,
                        reason=f"人工换床从 {source.code} 转入：{reason}", operator=operator,
                        allocation_id=new.id, admission_request_id=request.id)
        record_audit(db, action="REASSIGN_BED", user=operator,
                     object_type="bed_allocation", object_id=new.id,
                     detail={"old_allocation_id": old.id, "old_bed_id": source.id,
                             "new_allocation_id": new.id, "new_bed_id": target.id,
                             "reason": reason}, ip=ip, user_agent=user_agent)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(ErrorCode.BED_DOUBLE_BOOKED, "换床目标已发生并发占用") from exc
    except Exception:
        db.rollback()
        raise
    return get_allocation(db, new.id)

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
        request, alloc = _lock_alloc_and_request(db, allocation_id)

        assert_allocation_transition(alloc, AllocationStatus.ADMITTED)

        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()

        _assert_pair(alloc, bed, status=AllocationStatus.RESERVED, bed_status=BedStatus.RESERVED)
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
        request, alloc = _lock_alloc_and_request(db, allocation_id)

        assert_allocation_transition(alloc, AllocationStatus.DISCHARGED)

        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()

        _assert_pair(alloc, bed, status=AllocationStatus.ADMITTED, bed_status=BedStatus.OCCUPIED)
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
        request, alloc = _lock_alloc_and_request(db, allocation_id)

        assert_allocation_transition(alloc, AllocationStatus.CANCELLED)
        bed = db.execute(select(Bed).where(Bed.id == alloc.bed_id).with_for_update()).scalar_one()

        _assert_pair(alloc, bed, status=AllocationStatus.RESERVED, bed_status=BedStatus.RESERVED)
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
