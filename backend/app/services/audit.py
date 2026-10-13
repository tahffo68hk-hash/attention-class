"""审计服务。

两种写入方式：

* ``record_audit`` —— 与业务操作共用同一个事务，保证"业务成功 ⟺ 审计落库"。
* ``record_audit_standalone`` —— 使用独立会话立即提交，用于业务事务确定要回滚的
  场景（如越权访问、认证失败），保证失败操作同样留痕。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.audit import AuditLog
from app.models.enums import AuditResult
from app.models.user import User


def _payload(
    action: str,
    user: User | None,
    object_type: str | None,
    object_id: Any,
    result: AuditResult,
    detail: dict[str, Any] | None,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    return {
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "role": getattr(user, "role", None).value if getattr(user, "role", None) else None,
        "action": action,
        "object_type": object_type,
        "object_id": None if object_id is None else str(object_id),
        "result": result,
        "detail": detail,
        "ip": ip,
        "user_agent": (user_agent or "")[:255] or None,
    }


def record_audit(
    db: Session,
    *,
    action: str,
    user: User | None = None,
    object_type: str | None = None,
    object_id: Any = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        **_payload(action, user, object_type, object_id, result, detail, ip, user_agent)
    )
    db.add(entry)
    return entry


def record_audit_standalone(
    *,
    action: str,
    user: User | None = None,
    object_type: str | None = None,
    object_id: Any = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    session = get_session_factory()()
    try:
        session.add(
            AuditLog(
                **_payload(action, user, object_type, object_id, result, detail, ip, user_agent)
            )
        )
        session.commit()
    except Exception:  # 审计写入失败不应影响主流程返回
        session.rollback()
    finally:
        session.close()
