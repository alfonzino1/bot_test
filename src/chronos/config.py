"""Конфигурация приложения: pydantic-settings + .env.

Секреты читаются только отсюда и никогда не попадают в код или логи.
"""

from __future__ import annotations

from datetime import time
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from chronos.constants import (
    DEFAULT_AUTOSTOP_AT,
    DEFAULT_EVENING_DIGEST_AT,
    DEFAULT_MORNING_DIGEST_AT,
    DEFAULT_REMINDER_HORIZON_DAYS,
    DEFAULT_WEEKLY_REPORT_AT,
)

#: Корень репозитория (…/chronos), нужен для путей к БД и миграциям.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Настройки процесса. Значения по умолчанию — дев-френдли, прод — через .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: SecretStr = Field(default=SecretStr(""), alias="BOT_TOKEN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    #: Фоновая очередь логов: включай только если процесс реально многопоточный.
    log_enqueue: bool = Field(default=False, alias="LOG_ENQUEUE")
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(DATA_DIR / 'chronos.db').as_posix()}",
        alias="DATABASE_URL",
    )
    default_timezone: str = Field(default="Europe/Moscow", alias="DEFAULT_TIMEZONE")

    #: Пусто = бот открыт всем (single-user MVP). Список через запятую = белый список.
    allowed_telegram_ids_raw: str = Field(default="", alias="ALLOWED_TELEGRAM_IDS")

    morning_digest_at: time = Field(default=DEFAULT_MORNING_DIGEST_AT, alias="MORNING_DIGEST_AT")
    evening_digest_at: time = Field(default=DEFAULT_EVENING_DIGEST_AT, alias="EVENING_DIGEST_AT")
    autostop_at: time = Field(default=DEFAULT_AUTOSTOP_AT, alias="AUTOSTOP_AT")
    weekly_report_at: time = Field(default=DEFAULT_WEEKLY_REPORT_AT, alias="WEEKLY_REPORT_AT")
    reminder_horizon_days: int = Field(
        default=DEFAULT_REMINDER_HORIZON_DAYS, alias="REMINDER_HORIZON_DAYS", ge=1, le=60
    )

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Некорректный LOG_LEVEL: {value!r}")
        return level

    @property
    def allowed_telegram_ids(self) -> frozenset[int]:
        """Белый список Telegram ID (пустое множество = без ограничений)."""
        raw = self.allowed_telegram_ids_raw.strip()
        if not raw:
            return frozenset()
        return frozenset(int(part) for part in raw.replace(";", ",").split(",") if part.strip())

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def has_bot_token(self) -> bool:
        return bool(self.bot_token.get_secret_value().strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный доступ к настройкам (читает .env один раз за процесс)."""
    return Settings()  # type: ignore[call-arg]


def ensure_data_dir() -> Path:
    """Гарантирует существование каталога для SQLite-файла и отчётов."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
