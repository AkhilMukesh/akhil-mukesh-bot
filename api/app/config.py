from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias="GROQ_MODEL",
    )
    groq_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=120,
        validation_alias="GROQ_TIMEOUT_SECONDS",
    )
    cors_origins: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )
    chat_rate_limit: int = Field(
        default=30,
        gt=0,
        le=1000,
        validation_alias="CHAT_RATE_LIMIT",
    )
    chat_rate_window_seconds: int = Field(
        default=60,
        gt=0,
        le=3600,
        validation_alias="CHAT_RATE_WINDOW_SECONDS",
    )
    profile_path: Path = Field(
        default=PROJECT_ROOT / "api" / "app" / "data" / "profile.json",
        validation_alias="PROFILE_PATH",
    )

    @property
    def allowed_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
