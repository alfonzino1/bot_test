"""Модель события расписания (модуль A).

Одно событие = одна строка. Повторяемость описана правилом ``repeat_rule``,
вхождения вычисляются на лету, а конкретные вхождения можно подавить через
``exceptions`` (см. docs/DECISIONS.md D-07).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronos.constants import EventStatus, RepeatRule
from chronos.models.base import Base
from chronos.models.types import UTCDateTime, utcnow


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class ScheduleEvent(Base):
    """Разовое или повторяющееся событие в расписании пользователя."""

    __tablename__ = "schedule"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="end_after_start"),
        Index("ix_schedule_user_start", "user_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    #: Начало первого вхождения. Для повторяющихся событий — «якорь» серии.
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)

    #: none | daily | weekdays | weekly:MO,WE,FR
    repeat_rule: Mapped[str] = mapped_column(String(64), default=RepeatRule.NONE.value)
    #: Ключ категории либо свободная метка пользователя; None = «Без категории».
    category: Mapped[str | None] = mapped_column(String(64), default=None)

    #: Смещение напоминания в минутах до начала; NULL = «не надо» (ТЗ, модуль A).
    reminder_offset: Mapped[int | None] = mapped_column(default=None)

    status: Mapped[EventStatus] = mapped_column(
        SAEnum(
            EventStatus,
            name="event_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        default=EventStatus.PLANNED,
    )

    #: ISO-даты вхождений, которые нужно пропустить (перенос конкретного вхождения).
    exceptions: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    #: Сообщение с карточкой события — чтобы редактировать, а не спамить.
    message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)

    @property
    def is_recurring(self) -> bool:
        return self.repeat_rule != RepeatRule.NONE.value

    @property
    def duration_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScheduleEvent id={self.id} {self.title!r} start={self.start_at.isoformat()}>"


__all__ = ["ScheduleEvent"]
