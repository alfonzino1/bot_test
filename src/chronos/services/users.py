"""Сервис пользователя: онбординг, настройки, тишина, сброс данных.

Все изменения пользователя проходят через этот модуль — единый источник правды
по времени жизни настроек (docs/DECISIONS.md D-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time

from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import (
    ON,
    OFF,
    ReportFrequency,
    SettingKey,
    TrackingMode,
)
from chronos.logging_setup import logger
from chronos.models import User
from chronos.repositories import settings as settings_repo
from chronos.repositories import users as users_repo
from chronos.services import quiet
from chronos.utils.timezones import tz_for, tz_name


@dataclass(frozen=True, slots=True)
class UserSettings:
    """Снимок настроек для планировщика и экрана «Настройки»."""

    tz: str
    work_start: time
    work_end: time
    quiet_start: time
    quiet_end: time
    tracking_mode: TrackingMode
    report_frequency: ReportFrequency
    digests_morning: bool
    digests_evening: bool
    reminders_enabled: bool
    muted_until: datetime | None

    @property
    def is_muted(self) -> bool:
        return self.muted_until is not None


async def ensure_user(
    session: AsyncSession, *, telegram_id: int, name: str | None, default_tz: str
) -> tuple[User, bool]:
    """Гарантирует наличие пользователя. Возвращает (user, создан_только_что)."""
    user, created = await users_repo.get_or_create(
        session, telegram_id=telegram_id, name=name, tz=default_tz
    )
    if created:
        logger.info("Новый пользователь: telegram_id={}", telegram_id)
    return user, created


async def set_timezone(session: AsyncSession, user: User, tz: str) -> User:
    """Сохраняет таймзону (только валидную IANA-зону)."""
    zone = tz_for(tz)
    await users_repo.update_basics(session, user, tz=tz_name(zone))
    return user


async def set_name(session: AsyncSession, user: User, name: str) -> User:
    """Сохраняет имя пользователя."""
    return await users_repo.update_basics(session, user, name=name.strip()[:128])


async def set_tracking_mode(session: AsyncSession, user: User, mode: TrackingMode) -> User:
    """Меняет режим трекинга."""
    return await users_repo.update_tracking_mode(session, user, mode)


async def set_work_hours(session: AsyncSession, user: User, start: time, end: time) -> User:
    """Меняет рабочие часы."""
    return await users_repo.update_schedule_settings(
        session, user, work_start=start, work_end=end
    )


async def set_quiet_hours(session: AsyncSession, user: User, start: time, end: time) -> User:
    """Меняет тихий час."""
    return await users_repo.update_schedule_settings(
        session, user, quiet_start=start, quiet_end=end
    )


async def finish_onboarding(session: AsyncSession, user: User, *, name: str | None = None) -> User:
    """Завершает онбординг: после этого ``/start`` ведёт в меню (docs/DECISIONS.md D-01)."""
    if name:
        await users_repo.update_basics(session, user, name=name)
    await users_repo.mark_onboarded(session, user)
    logger.info("Онбординг завершён: user_id={} tz={}", user.id, user.tz)
    return user


async def mute_for(session: AsyncSession, user: User, duration: timedelta, *, now: datetime) -> datetime:
    """Включает ручную тишину на указанное время. Возвращает момент окончания (UTC)."""
    until = quiet.next_mute_until(duration, now_utc=now)
    await settings_repo.set_value(session, user.id, SettingKey.MUTE_UNTIL, until.isoformat())
    logger.info("Тишина включена: user_id={} до {}", user.id, until.isoformat())
    return until


async def unmute(session: AsyncSession, user: User) -> None:
    """Выключает ручную тишину."""
    await settings_repo.delete_key(session, user.id, SettingKey.MUTE_UNTIL)


async def set_report_frequency(
    session: AsyncSession, user: User, frequency: ReportFrequency
) -> None:
    """Как часто присылать итоги."""
    await settings_repo.set_value(
        session, user.id, SettingKey.REPORT_FREQUENCY, frequency.value
    )


async def set_digest(session: AsyncSession, user: User, *, morning: bool | None = None,
                     evening: bool | None = None) -> None:
    """Включает/выключает утренний и вечерний дайджест."""
    if morning is not None:
        await settings_repo.set_value(
            session, user.id, SettingKey.DIGEST_MORNING, ON if morning else OFF
        )
    if evening is not None:
        await settings_repo.set_value(
            session, user.id, SettingKey.DIGEST_EVENING, ON if evening else OFF
        )


async def get_settings(session: AsyncSession, user: User) -> UserSettings:
    """Собирает полный снимок настроек пользователя (для планировщика и UI)."""
    raw = await settings_repo.get_all(session, user.id)
    from chronos.services.quiet import mute_until

    frequency_raw = raw.get(SettingKey.REPORT_FREQUENCY.value, ReportFrequency.WEEKLY.value)
    try:
        frequency = ReportFrequency(frequency_raw)
    except ValueError:
        frequency = ReportFrequency.WEEKLY
    return UserSettings(
        tz=user.tz,
        work_start=user.work_start,
        work_end=user.work_end,
        quiet_start=user.quiet_start,
        quiet_end=user.quiet_end,
        tracking_mode=TrackingMode(user.tracking_mode),
        report_frequency=frequency,
        digests_morning=raw.get(SettingKey.DIGEST_MORNING.value, ON) == ON,
        digests_evening=raw.get(SettingKey.DIGEST_EVENING.value, ON) == ON,
        reminders_enabled=raw.get(SettingKey.REMINDERS_ENABLED.value, ON) == ON,
        muted_until=mute_until(raw),
    )


async def reset_all_data(session: AsyncSession, user: User) -> None:
    """Сбрасывает все данные пользователя (кнопка «Сбросить данные»)."""
    await users_repo.delete_all_data(session, user)
    logger.warning("Данные пользователя удалены: user_id={}", user.id)


__all__ = [
    "UserSettings",
    "ensure_user",
    "finish_onboarding",
    "get_settings",
    "mute_for",
    "reset_all_data",
    "set_digest",
    "set_name",
    "set_quiet_hours",
    "set_report_frequency",
    "set_timezone",
    "set_tracking_mode",
    "set_work_hours",
    "unmute",
]
