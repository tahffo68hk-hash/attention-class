"""认证接口。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, client_ip, user_agent
from app.core.config import settings
from app.core.errors import ErrorCode, UnauthorizedError
from app.core.security import create_access_token, verify_password
from app.models.enums import AuditAction, AuditResult
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import MessageOut
from app.services.audit import record_audit, record_audit_standalone
from app.services.serializers import user_read

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="登录获取访问令牌",
    description="演示账号见 README（admin / doctor01 / nurse01 / viewer01）。",
)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    user = db.execute(
        select(User).options(joinedload(User.doctor)).where(User.username == payload.username)
    ).unique().scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        record_audit_standalone(
            action=AuditAction.LOGIN_FAILED.value,
            user=None,
            object_type="user",
            object_id=payload.username,
            result=AuditResult.FAILURE,
            detail={"username": payload.username, "reason": "用户名或口令错误"},
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        raise UnauthorizedError("用户名或口令错误", ErrorCode.AUTH_INVALID_CREDENTIALS)

    if not user.is_active:
        record_audit_standalone(
            action=AuditAction.LOGIN_FAILED.value,
            user=user,
            object_type="user",
            object_id=user.id,
            result=AuditResult.FAILURE,
            detail={"reason": "账号已停用"},
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        raise UnauthorizedError("账号已被停用", ErrorCode.AUTH_INVALID_CREDENTIALS)

    user.last_login_at = datetime.now()
    record_audit(
        db,
        action=AuditAction.LOGIN.value,
        user=user,
        object_type="user",
        object_id=user.id,
        result=AuditResult.SUCCESS,
        detail={"username": user.username, "role": str(user.role)},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()

    token = create_access_token(user.username, str(user.role))
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_read(user),
    )


@router.get("/me", response_model=None, summary="获取当前登录用户")
def me(user: CurrentUser):
    return user_read(user)


@router.post("/logout", response_model=MessageOut, summary="退出登录（记录审计）")
def logout(request: Request, db: DbSession, user: CurrentUser) -> MessageOut:
    record_audit(
        db,
        action="LOGOUT",
        user=user,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return MessageOut(message="已退出登录")
