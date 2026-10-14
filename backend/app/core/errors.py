"""统一错误模型与异常处理器。

所有 API 错误响应统一为：

    {
      "code": "BED_NOT_AVAILABLE",
      "message": "床位已被占用或不可用",
      "detail": {...},
      "request_id": "..."
    }
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode:
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    ILLEGAL_STATE_TRANSITION = "ILLEGAL_STATE_TRANSITION"
    HARD_CONSTRAINT_VIOLATION = "HARD_CONSTRAINT_VIOLATION"
    BED_NOT_AVAILABLE = "BED_NOT_AVAILABLE"
    BED_DOUBLE_BOOKED = "BED_DOUBLE_BOOKED"
    REQUEST_ALREADY_ALLOCATED = "REQUEST_ALREADY_ALLOCATED"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    NO_BED_AVAILABLE = "NO_BED_AVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class BizError(Exception):
    """业务异常基类，携带统一的错误码与 HTTP 状态码。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFoundError(BizError):
    def __init__(self, message: str = "资源不存在", detail: Any | None = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, 404, detail)


class PermissionDeniedError(BizError):
    def __init__(self, message: str = "当前角色无权执行该操作", detail: Any | None = None) -> None:
        super().__init__(ErrorCode.PERMISSION_DENIED, message, 403, detail)


class UnauthorizedError(BizError):
    def __init__(self, message: str = "认证失败", code: str = ErrorCode.AUTH_TOKEN_INVALID) -> None:
        super().__init__(code, message, 401)


class ConflictError(BizError):
    def __init__(
        self,
        code: str = ErrorCode.DUPLICATE_RESOURCE,
        message: str = "资源冲突",
        detail: Any | None = None,
        status_code: int = 409,
    ) -> None:
        super().__init__(code, message, status_code, detail)


class StateTransitionError(BizError):
    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(ErrorCode.ILLEGAL_STATE_TRANSITION, message, 409, detail)


class HardConstraintError(BizError):
    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(ErrorCode.HARD_CONSTRAINT_VIOLATION, message, 422, detail)


def _payload(code: str, message: str, detail: Any, request_id: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "detail": detail,
        "request_id": request_id,
    }


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.detail, _request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                ErrorCode.VALIDATION_ERROR,
                "请求参数校验失败",
                {"errors": _jsonable_errors(exc.errors())},
                _request_id(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: ErrorCode.AUTH_TOKEN_INVALID,
            403: ErrorCode.PERMISSION_DENIED,
            404: ErrorCode.NOT_FOUND,
        }.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail), None, _request_id(request)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_payload(
                ErrorCode.INTERNAL_ERROR,
                "服务器内部错误",
                {"type": type(exc).__name__, "message": str(exc)},
                _request_id(request),
            ),
        )


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for err in errors:
        item = {k: v for k, v in err.items() if k != "ctx"}
        item["loc"] = [str(part) for part in err.get("loc", [])]
        out.append(item)
    return out
