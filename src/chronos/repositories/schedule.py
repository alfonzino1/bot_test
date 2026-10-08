"""Репозиторий событий расписания."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import EventStatus, RepeatRule
from chronos.models import ScheduleEvent


async def create_event(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    start_at: datetime,
    end_at: datetime,
    repeat_rule: str = RepeatRule.NONE.value,
    category: str | None = None,
    reminder_offset: int | None = None,
    status: EventStatus = EventStatus.PLANNED,
) -> ScheduleEvent:
    """Создаёт событие (разовое или серию)."""
    event = ScheduleEvent(
        user_id=user_id,
        title=title,
        start_at=start_at,
        end_at=end_at,
        repeat_rule=repeat_rule,
        category=category,
        reminder_offset=reminder_offset,
        status=status,
    )
    session.add(event)
    await session.flush()
    return event


async def get(session: AsyncSession, user_id: int, event_id: int) -> ScheduleEvent | None:
    """Событие пользователя по ID (проверяем владельца — задел под мультиюзера)."""
    result = await session.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id, ScheduleEvent.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def list_for_window(
    session: AsyncSession, user_id: int, window_start: datetime, window_end: datetime
) -> Sequence[ScheduleEvent]:
    """Кандидаты, которые могут иметь вхождение в окне.

    Разовые события фильтруются по пересечению интервалов, повторяющиеся —
    только по «якорь не позже конца окна»: их вхождения вычисляет сервис.
    """
    result = await session.execute(
        select(ScheduleEvent)
        .where(
            ScheduleEvent.user_id == user_id,
            or_(
                and_(
                    ScheduleEvent.repeat_rule == RepeatRule.NONE.value,
                    ScheduleEvent.start_at < window_end,
                    ScheduleEvent.end_at > window_start,
                ),
                and_(
                    ScheduleEvent.repeat_rule != RepeatRule.NONE.value,
                    ScheduleEvent.start_at <= window_end,
                ),
            ),
        )
        .order_by(ScheduleEvent.start_at)
    )
    return result.scalars().all()


async def list_recurring(session: AsyncSession, user_id: int) -> Sequence[ScheduleEvent]:
    """Все повторяющиеся события пользователя (нужны для материализации напоминаний)."""
    result = await session.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id,
            ScheduleEvent.repeat_rule != RepeatRule.NONE.value,
        )
    )
    return result.scalars().all()


async def list_with_reminders(
    session: AsyncSession, *, horizon_end: datetime, user_id: int | None = None
) -> Sequence[ScheduleEvent]:
    """События с напоминанием, у которых вхождение может попасть в горизонт."""
    statement = select(ScheduleEvent).where(
        ScheduleEvent.reminder_offset.is_not(None),
        ScheduleEvent.status.not_in((EventStatus.CANCELED, EventStatus.MOVED)),
        or_(
            ScheduleEvent.repeat_rule != RepeatRule.NONE.value,
            ScheduleEvent.start_at <= horizon_end,
        ),
    )
    if user_id is not None:
        statement = statement.where(ScheduleEvent.user_id == user_id)
    result = await session.execute(statement)
    return result.scalars().all()


async def set_status(
    session: AsyncSession, event: ScheduleEvent, status: EventStatus
) -> ScheduleEvent:
    """Меняет статус события (✅ Иду / ⏰ Опоздаю / ❌ Отменяю / 🔄 Перенести)."""
    event.status = status
    await session.flush()
    return event


async def set_times(
    session: AsyncSession, event: ScheduleEvent, *, start_at: datetime, end_at: datetime
) -> ScheduleEvent:
    """Переносит событие целиком (для разовых событий)."""
    event.start_at = start_at
    event.end_at = end_at
    await session.flush()
    return event


async def add_exception(session: AsyncSession, event: ScheduleEvent, iso_date: str) -> ScheduleEvent:
    """Подавляет конкретное вхождение серии (перенос одного дня)."""
    exceptions = list(event.exceptions or [])
    if iso_date not in exceptions:
        exceptions.append(iso_date)
        # Присваиваем новый список: SQLAlchemy отслеживает замену значения JSON.
        event.exceptions = exceptions
    await session.flush()
    return event


async def delete_event(session: AsyncSession, event: ScheduleEvent) -> None:
    """Удаляет событие вместе с напоминаниями (FK ON DELETE CASCADE)."""
    await session.delete(event)
    await session.flush()


async def delete_all_for_user(session: AsyncSession, user_id: int) -> None:
    """Удаляет все события пользователя."""
    await session.execute(delete(ScheduleEvent).where(ScheduleEvent.user_id == user_id))
    await session.flush()


__all__ = [
    "add_exception",
    "create_event",
    "delete_all_for_user",
    "delete_event",
    "get",
    "list_for_window",
    "list_recurring",
    "list_with_reminders",
    "set_status",
    "set_times",
]
