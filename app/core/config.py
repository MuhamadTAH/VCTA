import shutil
from pathlib import Path
from pydantic import model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data/app.db")
    FFMPEG_PATH: str = Field(default="ffmpeg")
    OPENAI_API_KEY: str | None = Field(default=None)
    ANTHROPIC_API_KEY: str | None = Field(default=None)
    STORE_CONTEXT_MAX_LENGTH: int = Field(default=5000)
    VIDEO_JOB_TIMEOUT_SECONDS: int = Field(default=3600)
    STORE_URL_BASE: str = Field(default="https://example.com")
    FCM_SERVER_KEY: str | None = Field(default=None)
    WHATSAPP_GATEWAY_URL: str | None = Field(default=None)
    WHATSAPP_API_KEY: str | None = Field(default=None)
    VAPID_PUBLIC_KEY: str | None = Field(default=None)
    MINIMAX_API_KEY: str | None = Field(default=None)
    MINIMAX_API_BASE_URL: str = Field(default="https://api.minimax.io/v1")
    LLM_MODEL: str = Field(default="minimax-text-01")
    TELEGRAM_BOT_TOKEN: str | None = Field(default=None)
    TELEGRAM_BOT_USERNAME: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_system_dependencies(self) -> "Settings":
        if not shutil.which(self.FFMPEG_PATH):
            raise SystemExit(f"[CRITICAL] ffmpeg not found at path: {self.FFMPEG_PATH}. Install ffmpeg and ensure it is in PATH.")
        if not self.OPENAI_API_KEY and not self.ANTHROPIC_API_KEY and not self.MINIMAX_API_KEY:
            raise SystemExit("[CRITICAL] At least one AI API key must be set: OPENAI_API_KEY, ANTHROPIC_API_KEY, or MINIMAX_API_KEY")
        return self


_cached_settings: Settings | None = None


def get_settings() -> Settings:
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = Settings()
    return _cached_settings


def get_db_path() -> Path:
    return Path(get_settings().DATABASE_URL.replace("sqlite+aiosqlite:///", "")).resolve()