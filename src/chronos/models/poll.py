"""Модели напоминаний и опросов.

Обе таблицы идемпотентны по построению: уникальный ключ не даёт отправить
одно и то же дважды, даже если джоб запустился повторно (ТЗ, раздел 6).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronos.constants import PollKind, PollStatus, ReminderStatus
from chronos.models.base import Base
from chronos.models.types import UTCDateTime, utcnow


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class Reminder(Base):
    """Запланированное напоминание по конкретному вхождению события."""

    __tablename__ = "reminders"
    __table_args__ = (
        # Идемпотентность: одно напоминание на вхождение (docs/DECISIONS.md D-07).
        UniqueConstraint("schedule_id", "occurrence_start_at", name="schedule_occurrence"),
        Index("ix_reminders_status_send_at", "status", "send_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedule.id", ondelete="CASCADE"), index=True
    )

    #: Исходное время вхождения (UTC) — неизменно, ключ идемпотентности.
    occurrence_start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    send_at: Mapped[datetime] = mapped_column(UTCDateTime)

    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(
            ReminderStatus,
            name="reminder_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        default=ReminderStatus.PENDING,
    )
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reminder id={self.id} sch={self.schedule_id} send_at={self.send_at.isoformat()}>"


class Poll(Base):
    """Опрос пользователя: пассивный (раз в час) или контекстный (по событию)."""

    __tablename__ = "polls"
    __table_args__ = (
        # Один опрос данного вида на часовой слот — защита от дублей (D-06).
        UniqueConstraint("user_id", "kind", "slot_at", name="user_kind_slot"),
        Index("ix_polls_user_sent_at", "user_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    kind: Mapped[PollKind] = mapped_column(
        SAEnum(
            PollKind,
            name="poll_kind",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        )
    )
    #: Начало часового слота (UTC), к которому относится опрос.
    slot_at: Mapped[datetime] = mapped_column(UTCDateTime)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    #: Ключ категории, ``__same__``, ``__skip__`` либо NULL.
    answer: Mapped[str | None] = mapped_column(String(64), default=None)

    status: Mapped[PollStatus] = mapped_column(
        SAEnum(
            PollStatus,
            name="poll_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        default=PollStatus.PENDING,
    )

    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule.id", ondelete="SET NULL"), default=None
    )
    message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Poll id={self.id} kind={self.kind} status={self.status}>"


__all__ = ["Poll", "Reminder"]
