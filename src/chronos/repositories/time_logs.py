"""Репозиторий записей времени (включая активный таймер)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import LogSource
from chronos.models import TimeLog


async def create_log(
    session: AsyncSession,
    *,
    user_id: int,
    category: str,
    start_at: datetime,
    end_at: datetime | None = None,
    note: str | None = None,
    source: LogSource = LogSource.MANUAL,
    schedule_id: int | None = None,
    message_id: int | None = None,
) -> TimeLog:
    """Создаёт запись времени. ``end_at=None`` означает запущенный таймер."""
    log = TimeLog(
        user_id=user_id,
        category=category,
        start_at=start_at,
        end_at=end_at,
        note=note,
        source=source,
        schedule_id=schedule_id,
        message_id=message_id,
    )
    session.add(log)
    await session.flush()
    return log


async def get(session: AsyncSession, user_id: int, log_id: int) -> TimeLog | None:
    """Запись времени пользователя по ID."""
    result = await session.execute(
        select(TimeLog).where(TimeLog.id == log_id, TimeLog.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def active_for_user(session: AsyncSession, user_id: int) -> TimeLog | None:
    """Активный таймер пользователя (не более одного — гарантия индекса БД)."""
    result = await session.execute(
        select(TimeLog).where(TimeLog.user_id == user_id, TimeLog.end_at.is_(None))
    )
    return result.scalars().first()


async def list_active(session: AsyncSession) -> Sequence[TimeLog]:
    """Все активные таймеры (для автостопа в 23:00)."""
    result = await session.execute(select(TimeLog).where(TimeLog.end_at.is_(None)))
    return result.scalars().all()


async def list_for_window(
    session: AsyncSession, user_id: int, window_start: datetime, window_end: datetime
) -> Sequence[TimeLog]:
    """Записи, пересекающие окно. Незакрытые записи считаются идущими (D-05)."""
    result = await session.execute(
        select(TimeLog)
        .where(
            TimeLog.user_id == user_id,
            TimeLog.start_at < window_end,
            (TimeLog.end_at.is_(None)) | (TimeLog.end_at > window_start),
        )
        .order_by(TimeLog.start_at)
    )
    return result.scalars().all()


async def list_between(
    session: AsyncSession,
    user_id: int,
    window_start: datetime,
    window_end: datetime,
) -> Sequence[TimeLog]:
    """Записи, начавшиеся внутри окна (для «что было час назад»)."""
    result = await session.execute(
        select(TimeLog)
        .where(
            TimeLog.user_id == user_id,
            TimeLog.start_at >= window_start,
            TimeLog.start_at < window_end,
        )
        .order_by(TimeLog.start_at)
    )
    return result.scalars().all()


async def last_finished(session: AsyncSession, user_id: int, before: datetime) -> TimeLog | None:
    """Последняя завершённая запись до момента (для «то же, что час назад»)."""
    result = await session.execute(
        select(TimeLog)
        .where(TimeLog.user_id == user_id, TimeLog.end_at.is_not(None), TimeLog.end_at <= before)
        .order_by(TimeLog.end_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def close_log(
    session: AsyncSession, log: TimeLog, *, end_at: datetime, note: str | None = None
) -> TimeLog:
    """Останавливает таймер: проставляет конец (и заметку, если передана)."""
    log.end_at = end_at
    if note is not None:
        log.note = note
    await session.flush()
    return log


async def set_note(session: AsyncSession, log: TimeLog, note: str) -> TimeLog:
    """Дописывает заметку к записи."""
    log.note = note
    await session.flush()
    return log


async def set_category(session: AsyncSession, log: TimeLog, category: str) -> TimeLog:
    """Меняет категорию записи (когда пользователь выбрал другую кнопку)."""
    log.category = category
    await session.flush()
    return log


async def set_message_id(session: AsyncSession, log: TimeLog, message_id: int | None) -> TimeLog:
    """Запоминает сообщение таймера, чтобы редактировать его, а не слать новое."""
    log.message_id = message_id
    await session.flush()
    return log


async def delete_log(session: AsyncSession, log: TimeLog) -> None:
    """Удаляет запись времени."""
    await session.delete(log)
    await session.flush()


__all__ = [
    "active_for_user",
    "close_log",
    "create_log",
    "delete_log",
    "get",
    "last_finished",
    "list_active",
    "list_between",
    "list_for_window",
    "set_category",
    "set_message_id",
    "set_note",
]
