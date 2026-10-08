"""Репозиторий напоминаний.

Идемпотентность обеспечена уникальным ключом ``(schedule_id, occurrence_start_at)``:
повторная материализация не создаёт дублей (docs/DECISIONS.md D-07).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import ReminderStatus
from chronos.models import Reminder


async def get_by_id(session: AsyncSession, reminder_id: int) -> Reminder | None:
    """Напоминание по ID (из callback-данных кнопки)."""
    return await session.get(Reminder, reminder_id)


async def ensure_pending(
    session: AsyncSession,
    *,
    user_id: int,
    schedule_id: int,
    occurrence_start_at: datetime,
    send_at: datetime,
) -> Reminder:
    """Создаёт напоминание, если такого ещё нет; возвращает существующее иначе."""
    existing = await session.execute(
        select(Reminder).where(
            Reminder.schedule_id == schedule_id,
            Reminder.occurrence_start_at == occurrence_start_at,
        )
    )
    reminder = existing.scalar_one_or_none()
    if reminder is not None:
        # Пересчитываем время отправки, если событие перенесли (статус не меняем).
        if reminder.status is ReminderStatus.PENDING and reminder.send_at != send_at:
            reminder.send_at = send_at
            await session.flush()
        return reminder
    reminder = Reminder(
        user_id=user_id,
        schedule_id=schedule_id,
        occurrence_start_at=occurrence_start_at,
        send_at=send_at,
        status=ReminderStatus.PENDING,
    )
    session.add(reminder)
    await session.flush()
    return reminder


async def due(session: AsyncSession, now: datetime, *, limit: int = 100) -> Sequence[Reminder]:
    """Напоминания, которые пора отправить (``send_at <= now`` и статус pending)."""
    result = await session.execute(
        select(Reminder)
        .where(Reminder.status == ReminderStatus.PENDING, Reminder.send_at <= now)
        .order_by(Reminder.send_at)
        .limit(limit)
    )
    return result.scalars().all()


async def mark_sent(session: AsyncSession, reminder: Reminder, *, sent_at: datetime) -> Reminder:
    """Отмечает напоминание отправленным."""
    reminder.status = ReminderStatus.SENT
    reminder.sent_at = sent_at
    await session.flush()
    return reminder


async def mark_canceled(session: AsyncSession, reminder: Reminder) -> Reminder:
    """Отменяет напоминание (событие отменено или перенесено)."""
    reminder.status = ReminderStatus.CANCELED
    await session.flush()
    return reminder


async def cancel_future_for_event(session: AsyncSession, schedule_id: int, *, after: datetime) -> int:
    """Отменяет все будущие напоминания события. Возвращает количество отменённых."""
    result = await session.execute(
        select(Reminder).where(
            Reminder.schedule_id == schedule_id,
            Reminder.status == ReminderStatus.PENDING,
            Reminder.send_at > after,
        )
    )
    reminders = list(result.scalars().all())
    for reminder in reminders:
        reminder.status = ReminderStatus.CANCELED
    await session.flush()
    return len(reminders)


async def cancel_for_occurrence(
    session: AsyncSession, schedule_id: int, occurrence_start_at: datetime
) -> int:
    """Отменяет напоминание конкретного вхождения (перенос одного дня серии)."""
    result = await session.execute(
        select(Reminder).where(
            Reminder.schedule_id == schedule_id,
            Reminder.occurrence_start_at == occurrence_start_at,
            Reminder.status == ReminderStatus.PENDING,
        )
    )
    reminders = list(result.scalars().all())
    for reminder in reminders:
        reminder.status = ReminderStatus.CANCELED
    await session.flush()
    return len(reminders)


async def list_for_event(session: AsyncSession, schedule_id: int) -> Sequence[Reminder]:
    """Все напоминания события (для отладки и тестов)."""
    result = await session.execute(
        select(Reminder)
        .where(Reminder.schedule_id == schedule_id)
        .order_by(Reminder.send_at)
    )
    return result.scalars().all()


async def delete_older_than(session: AsyncSession, moment: datetime) -> int:
    """Чистит отработавшие напоминания (гигиена БД: не храним лишнее)."""
    result = await session.execute(
        delete(Reminder).where(
            Reminder.send_at < moment,
            Reminder.status != ReminderStatus.PENDING,
        )
    )
    await session.flush()
    return int(result.rowcount or 0)


__all__ = [
    "cancel_for_occurrence",
    "cancel_future_for_event",
    "delete_older_than",
    "due",
    "ensure_pending",
    "get_by_id",
    "list_for_event",
    "mark_canceled",
    "mark_sent",
]
