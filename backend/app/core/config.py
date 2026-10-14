"""应用配置。

所有配置均可通过环境变量或 backend/.env 覆盖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "医院床位智能分配与住院入院预办理系统"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # 数据库：本项目默认指向隔离的本地 MySQL 实例（3307）
    DATABASE_URL: str = (
        "mysql+pymysql://hospital_app:hospital_pwd_2026@127.0.0.1:3307/hospital?charset=utf8mb4"
    )
    TEST_DATABASE_URL: str = (
        "mysql+pymysql://hospital_app:hospital_pwd_2026@127.0.0.1:3307/hospital_test?charset=utf8mb4"
    )
    SQL_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 30

    # 安全
    SECRET_KEY: str = "dev-secret-please-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # P2 辅助解释：默认只用确定性规则；外部模型默认禁用，
    # 必须同时满足「后端开启 + 请求显式确认」才会真正外发（测试永不调用）。
    ASSISTANT_EXTERNAL_ENABLED: bool = False
    ASSISTANT_ENDPOINT: str = "https://api.openai.com/v1/chat/completions"
    ASSISTANT_API_KEY: str = ""
    ASSISTANT_MODEL: str = ""

    # 脱敏
    MASK_BY_DEFAULT: bool = True

    # 逗号分隔字符串：避免 pydantic-settings 对复杂类型做 JSON 解析
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    )

    @property
    def cors_origins(self) -> list[str]:
        """把逗号分隔的字符串解析为列表。"""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


settings = Settings()
