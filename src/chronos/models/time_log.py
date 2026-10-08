"""Модель записи времени (модуль B).

Активный таймер — строка с ``end_at IS NULL``, ровно одна на пользователя
(частичный уникальный индекс), см. docs/DECISIONS.md D-05 и D-06.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronos.constants import LogSource
from chronos.models.base import Base
from chronos.models.types import UTCDateTime, utcnow


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class TimeLog(Base):
    """Запись о том, на что ушло время.

    ``end_at is None`` означает идущий таймер. ``schedule_id`` связывает запись
    с планом (нужно для «план vs факт» и контекстных опросов).
    """

    __tablename__ = "time_logs"
    __table_args__ = (
        CheckConstraint("end_at IS NULL OR end_at > start_at", name="end_after_start"),
        Index("ix_time_logs_user_start", "user_id", "start_at"),
        # Гарантия «не более одного активного таймера на пользователя».
        Index(
            "uq_time_logs_active_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("end_at IS NULL"),
            postgresql_where=text("end_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    #: Ключ категории (или свободная метка пользователя).
    category: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    note: Mapped[str | None] = mapped_column(String(500), default=None)

    source: Mapped[LogSource] = mapped_column(
        SAEnum(
            LogSource,
            name="log_source",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        default=LogSource.MANUAL,
    )

    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule.id", ondelete="SET NULL"), default=None
    )
    #: Telegram message id «одного редактируемого сообщения» активного таймера.
    message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def is_active(self) -> bool:
        return self.end_at is None

    def duration_minutes(self, *, now: datetime) -> int:
        """Длительность записи в минутах; для активного таймера — до ``now``."""
        end = self.end_at or now
        return max(0, int((end - self.start_at).total_seconds() // 60))

    def __repr__(self) -> str:  # pragma: no cover
        state = "active" if self.is_active else self.end_at.isoformat()  # type: ignore[union-attr]
        return f"<TimeLog id={self.id} cat={self.category} {self.start_at.isoformat()} → {state}>"


__all__ = ["TimeLog"]
