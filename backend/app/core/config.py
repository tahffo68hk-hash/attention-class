"""应用配置。

所有配置均可通过环境变量或 backend/.env 覆盖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
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

    @model_validator(mode="before")
    @classmethod
    def _blank_env_value_uses_default(cls, data: object) -> object:
        """把空字符串（或纯空白）视为「未配置」，回落到字段默认值。

        pydantic-settings 会把 `.env` 里的 `KEY=` 当作"已设置的空字符串"，
        对于 `float | None` 这类字段会直接抛解析错误。而本项目 `.env.example`
        对可选费率正是留空表示「不估价」，因此这里统一把空值剔除。
        """
        if isinstance(data, dict):
            return {
                key: value
                for key, value in data.items()
                if not (isinstance(value, str) and not value.strip())
            }
        return data

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

    # P4 DeepSeek：默认禁用，API key 只在本机 backend/.env 存放，绝不返回给前端。
    DEEPSEEK_EXTERNAL_ENABLED: bool = False
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_TIMEOUT_SECONDS: float = 15.0
    DEEPSEEK_MAX_OUTPUT_TOKENS: int = 500
    # 费用为可选的 CNY 估算，不是官方账单。由使用者按当前峰/谷价格显式配置。
    DEEPSEEK_INPUT_MISS_CNY_PER_M: float | None = None
    DEEPSEEK_INPUT_HIT_CNY_PER_M: float | None = None
    DEEPSEEK_OUTPUT_CNY_PER_M: float | None = None

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
