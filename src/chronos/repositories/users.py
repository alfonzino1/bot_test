"""Репозиторий пользователей."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import (
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_WORK_END,
    DEFAULT_WORK_START,
    TrackingMode,
)
from chronos.models import Poll, Reminder, ScheduleEvent, Setting, TimeLog, User
from chronos.models.types import utcnow


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """Пользователь по Telegram ID (основной вход в бота)."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Пользователь по внутреннему ID."""
    return await session.get(User, user_id)


async def get_or_create(
    session: AsyncSession,
    *,
    telegram_id: int,
    name: str | None = None,
    tz: str = "Europe/Moscow",
) -> tuple[User, bool]:
    """Возвращает пользователя и признак «создан только что».

    Идемпотентно: повторный вызов не меняет существующую запись.
    """
    existing = await get_by_telegram_id(session, telegram_id)
    if existing is not None:
        return existing, False
    user = User(
        telegram_id=telegram_id,
        name=name,
        tz=tz,
        work_start=DEFAULT_WORK_START,
        work_end=DEFAULT_WORK_END,
        quiet_start=DEFAULT_QUIET_START,
        quiet_end=DEFAULT_QUIET_END,
        tracking_mode=TrackingMode.BOTH,
    )
    session.add(user)
    await session.flush()
    return user, True


async def list_onboarded(session: AsyncSession) -> Sequence[User]:
    """Все прошедшие онбординг (нужно планировщику для рассылок)."""
    result = await session.execute(select(User).where(User.onboarded_at.is_not(None)))
    return result.scalars().all()


async def update_basics(
    session: AsyncSession,
    user: User,
    *,
    name: str | None = None,
    tz: str | None = None,
) -> User:
    """Обновляет имя и/или таймзону, только переданные поля."""
    if name is not None:
        user.name = name
    if tz is not None:
        user.tz = tz
    await session.flush()
    return user


async def update_schedule_settings(
    session: AsyncSession,
    user: User,
    *,
    work_start: time | None = None,
    work_end: time | None = None,
    quiet_start: time | None = None,
    quiet_end: time | None = None,
) -> User:
    """Обновляет рабочие часы и тихий час."""
    if work_start is not None:
        user.work_start = work_start
    if work_end is not None:
        user.work_end = work_end
    if quiet_start is not None:
        user.quiet_start = quiet_start
    if quiet_end is not None:
        user.quiet_end = quiet_end
    await session.flush()
    return user


async def update_tracking_mode(
    session: AsyncSession, user: User, mode: TrackingMode
) -> User:
    """Меняет режим трекинга (ручной / авто / оба)."""
    user.tracking_mode = mode
    await session.flush()
    return user


async def mark_onboarded(session: AsyncSession, user: User, *, at: datetime | None = None) -> User:
    """Фиксирует завершение онбординга (после этого /start ведёт в меню)."""
    user.onboarded_at = at or utcnow()
    await session.flush()
    return user


async def delete_all_data(session: AsyncSession, user: User) -> None:
    """Полный сброс данных пользователя («Сбросить данные» в настройках).

    Удаляются события, записи времени, напоминания, опросы и настройки.
    Сам пользователь остаётся, но онбординг нужно пройти заново.
    """
    user_id = user.id
    for model in (Reminder, Poll, TimeLog, ScheduleEvent, Setting):
        await session.execute(delete(model).where(model.user_id == user_id))
    # Имя не трогаем: это не данные трекинга. Онбординг проходим заново.
    user.onboarded_at = None
    await session.flush()


__all__ = [
    "delete_all_data",
    "get_by_id",
    "get_by_telegram_id",
    "get_or_create",
    "list_onboarded",
    "mark_onboarded",
    "update_basics",
    "update_schedule_settings",
    "update_tracking_mode",
]
