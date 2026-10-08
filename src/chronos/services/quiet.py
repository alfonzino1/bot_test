"""Тишина: тихий час, внерабочее время и ручной mute.

Единая точка правды для всех задач планировщика (docs/DECISIONS.md D-09):
если задача хочет что-то отправить пользователю, она обязана спросить здесь.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from chronos.models import User
from chronos.utils.timezones import tz_for, is_within, tz_name


def is_quiet_now(user: User, *, now_utc: datetime) -> bool:
    """Идёт ли тихий час пользователя прямо сейчас (локальное время)."""
    local = now_utc.astimezone(tz_for(user.tz))
    return is_within(local.time(), user.quiet_start, user.quiet_end)


def is_work_time(user: User, *, now_utc: datetime) -> bool:
    """Рабочие часы (когда можно беспокоить) по локальному времени."""
    local = now_utc.astimezone(tz_for(user.tz))
    return is_within(local.time(), user.work_start, user.work_end)


def is_muted(settings: dict[str, str], *, now_utc: datetime) -> bool:
    """Активна ли ручная тишина ``/mute``."""
    moment = mute_until(settings)
    return moment is not None and moment > now_utc


def mute_until(settings: dict[str, str]) -> datetime | None:
    """Момент окончания ручной тишины (UTC) или None."""
    from chronos.constants import SettingKey

    raw = settings.get(SettingKey.MUTE_UNTIL.value)
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        from datetime import UTC

        return moment.replace(tzinfo=UTC)
    return moment


def is_silent(user: User, settings: dict[str, str], *, now_utc: datetime) -> bool:
    """Полная проверка: нельзя ли сейчас беспокоить пользователя.

    Ручной mute подавляет всё, тихий час — только проактивные сообщения.
    """
    return is_muted(settings, now_utc=now_utc) or is_quiet_now(user, now_utc=now_utc)


def can_ask_passively(user: User, settings: dict[str, str], *, now_utc: datetime) -> bool:
    """Можно ли задать пассивный вопрос: рабочие часы, не тихо, не mute, не задавали час назад."""
    return (
        not is_silent(user, settings, now_utc=now_utc)
        and is_work_time(user, now_utc=now_utc)
    )


def describe_silence(user: User, settings: dict[str, str], *, now_utc: datetime) -> str | None:
    """Человекочитаемое описание тишины для настроек («до 14:30»)."""
    from chronos.utils.formatting import format_time, humanize_datetime

    moment = mute_until(settings)
    if moment and moment > now_utc:
        local = moment.astimezone(tz_for(user.tz))
        return humanize_datetime(local, now_utc.astimezone(tz_for(user.tz)))
    if is_quiet_now(user, now_utc=now_utc):
        return f"{format_time(user.quiet_start)}–{format_time(user.quiet_end)}"
    return None


def next_mute_until(duration: timedelta, *, now_utc: datetime) -> datetime:
    """Момент окончания тишины для ``/mute 2h``."""
    return now_utc + duration


def next_allowed_moment(user: User, settings: dict[str, str], *, now_utc: datetime) -> datetime:
    """Ближайший момент, когда пользователя можно беспокоить.

    Используется вместо отбрасывания сообщений: напоминание не теряется,
    а переносится на конец тихого часа или ручной тишины.
    """
    from datetime import UTC

    moment = now_utc
    muted = mute_until(settings)
    if muted is not None and muted > moment:
        moment = muted
    if is_quiet_now(user, now_utc=moment):
        tz = tz_for(user.tz)
        local = moment.astimezone(tz)
        quiet_end_local = datetime.combine(local.date(), user.quiet_end, tzinfo=tz)
        if quiet_end_local <= local:
            quiet_end_local += timedelta(days=1)
        moment = quiet_end_local.astimezone(UTC)
    return moment


def zone_name(user: User) -> str:
    """IANA-имя зоны пользователя (для логов и настроек)."""
    return tz_name(tz_for(user.tz))


__all__ = [
    "can_ask_passively",
    "describe_silence",
    "is_muted",
    "is_quiet_now",
    "is_silent",
    "is_work_time",
    "mute_until",
    "next_allowed_moment",
    "next_mute_until",
    "zone_name",
]
