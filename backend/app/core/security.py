"""口令散列与 JWT 令牌。

口令散列使用标准库 PBKDF2-HMAC-SHA256（20 万次迭代），不引入第三方依赖，
避免原型阶段 bcrypt 二进制轮子的安装问题。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings

_PBKDF2_ITERATIONS = 200_000
_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """生成 `pbkdf2_sha256$迭代次数$salt$hash` 形式的散列串。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "$".join(
        [
            _PREFIX,
            str(_PBKDF2_ITERATIONS),
            base64.b64encode(salt).decode(),
            base64.b64encode(dk).decode(),
        ]
    )


def verify_password(password: str, hashed: str) -> bool:
    try:
        algorithm, iterations, salt_b64, hash_b64 = hashed.split("$")
        if algorithm != _PREFIX:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def create_access_token(
    subject: str,
    role: str,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
