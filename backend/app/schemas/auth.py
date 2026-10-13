"""认证相关模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, examples=["admin"])
    password: str = Field(..., min_length=4, max_length=128, examples=["admin123"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserRead"


class UserRead(ORMModel):
    id: int
    username: str
    full_name: str
    role: str
    role_label: str | None = None
    is_active: bool
    doctor_id: int | None = None
    department_id: int | None = None


TokenResponse.model_rebuild()
