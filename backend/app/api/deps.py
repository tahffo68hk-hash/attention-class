"""认证、鉴权与通用依赖。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ErrorCode, PermissionDeniedError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import AuditAction, AuditResult, UserRole
from app.models.user import User
from app.services.audit import record_audit_standalone

bearer_scheme = HTTPBearer(auto_error=False, description="登录后获得的 Bearer Token")


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("缺少访问令牌，请先登录", ErrorCode.AUTH_TOKEN_INVALID)

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        record_audit_standalone(
            action=AuditAction.LOGIN_FAILED.value,
            result=AuditResult.FAILURE,
            detail={"reason": "token_expired"},
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        raise UnauthorizedError("访问令牌已过期，请重新登录", ErrorCode.AUTH_TOKEN_EXPIRED) from exc
    except jwt.PyJWTError as exc:
        record_audit_standalone(
            action=AuditAction.LOGIN_FAILED.value,
            result=AuditResult.FAILURE,
            detail={"reason": "token_invalid"},
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        raise UnauthorizedError("访问令牌无效", ErrorCode.AUTH_TOKEN_INVALID) from exc

    username = payload.get("sub")
    user = db.execute(
        select(User).options(joinedload(User.doctor)).where(User.username == username)
    ).unique().scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("令牌对应的用户不存在", ErrorCode.AUTH_TOKEN_INVALID)
    if not user.is_active:
        raise UnauthorizedError("账号已被停用", ErrorCode.AUTH_TOKEN_INVALID)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: UserRole | str) -> Callable[[Request, User], User]:
    """生成角色校验依赖；不满足时抛出 403 并写入审计。"""
    allowed = {r.value if isinstance(r, UserRole) else str(r) for r in roles}

    def _dependency(request: Request, user: CurrentUser) -> User:
        role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
        if role_value not in allowed:
            record_audit_standalone(
                action=AuditAction.PERMISSION_DENIED.value,
                user=user,
                object_type="endpoint",
                object_id=request.url.path,
                result=AuditResult.FAILURE,
                detail={
                    "required_roles": sorted(allowed),
                    "actual_role": role_value,
                    "method": request.method,
                    "path": request.url.path,
                },
                ip=client_ip(request),
                user_agent=user_agent(request),
            )
            raise PermissionDeniedError(
                f"当前角色「{role_value}」无权执行该操作，需要角色：{'/'.join(sorted(allowed))}"
            )
        return user

    return _dependency
