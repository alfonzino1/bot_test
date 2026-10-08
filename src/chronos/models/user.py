"""Модель пользователя.

Для single-user MVP таблица одна, но схема готова к мультиюзеру: всё связанное
хранит ``user_id`` (см. docs/DECISIONS.md D-02 — источник правды по настройкам).
"""

from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import BigInteger, Enum as SAEnum, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from chronos.constants import (
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_WORK_END,
    DEFAULT_WORK_START,
    TrackingMode,
)
from chronos.models.base import Base
from chronos.models.types import UTCDateTime, utcnow


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Хранить в БД значения enum-member'ов (``work``), а не их имена (``WORK``)."""
    return [member.value for member in enum_cls]


class User(Base):
    """Пользователь бота и его базовые настройки."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128))

    tz: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    work_start: Mapped[time] = mapped_column(Time, default=DEFAULT_WORK_START)
    work_end: Mapped[time] = mapped_column(Time, default=DEFAULT_WORK_END)
    quiet_start: Mapped[time] = mapped_column(Time, default=DEFAULT_QUIET_START)
    quiet_end: Mapped[time] = mapped_column(Time, default=DEFAULT_QUIET_END)

    tracking_mode: Mapped[TrackingMode] = mapped_column(
        SAEnum(
            TrackingMode,
            name="tracking_mode",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        default=TrackingMode.BOTH,
    )

    #: Момент завершения онбординга. None → показываем онбординг при /start (D-01).
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def is_onboarded(self) -> bool:
        return self.onboarded_at is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} tg={self.telegram_id} tz={self.tz}>"


__all__ = ["User"]
