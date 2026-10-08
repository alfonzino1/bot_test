"""Напоминания: подбор готовых к отправке и сборка текстов.

Джоб планировщика только отправляет то, что вернул этот сервис: вся логика
(тишина, идемпотентность, текст) — здесь.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import REMINDER_IMMEDIATE, ReminderStatus, SettingKey
from chronos.i18n import t
from chronos.logging_setup import logger
from chronos.models import Reminder, ScheduleEvent, User
from chronos.repositories import reminders as reminders_repo
from chronos.repositories import schedule as schedule_repo
from chronos.repositories import settings as settings_repo
from chronos.repositories import users as users_repo
from chronos.services import quiet
from chronos.utils.timezones import tz_for


@dataclass(slots=True)
class DueReminder:
    """Напоминание, готовое к отправке в Telegram."""

    reminder: Reminder
    event: ScheduleEvent
    user: User
    occurrence_local: datetime
    minutes_before: int
    text: str


def build_reminder_text(
    *, title: str, minutes_before: int, start_local: datetime, category: str | None
) -> str:
    """Текст напоминания по микрокопирайту: «⏰ Через 15 мин: Созвон с командой».

    Категория добавляется отдельной строкой, чтобы название осталось читаемым.
    """
    from chronos.utils.formatting import format_time

    if minutes_before <= REMINDER_IMMEDIATE:
        head = t("reminder.now", title=title)
    else:
        head = t("reminder.in_minutes", minutes=minutes_before, title=title)
    lines = [head, f"🕐 {format_time(start_local)}"]
    if category:
        from chronos.constants import category_label

        lines.append(category_label(category))
    return "\n".join(lines)


async def postpone(
    session: AsyncSession, reminder: Reminder, *, until: datetime
) -> Reminder:
    """Откладывает отправку до момента ``until`` (тихий час или ручная тишина)."""
    reminder.send_at = until
    await session.flush()
    logger.info(
        "Напоминание отложено до {}: reminder_id={}", until.isoformat(), reminder.id
    )
    return reminder


async def collect_due(session: AsyncSession, *, now_utc: datetime) -> list[DueReminder]:
    """Собирает напоминания, готовые к отправке.

    Каждое просроченное напоминание либо откладывается (тишина), либо
    помечается отправленным (если событие устарело).
    """
    due = await reminders_repo.due(session, now_utc)
    ready: list[DueReminder] = []
    for reminder in due:
        event = await schedule_repo.get(session, reminder.user_id, reminder.schedule_id)
        user = await users_repo.get_by_id(session, reminder.user_id)
        if event is None or user is None:
            # Событие удалено — напоминание больше не нужно.
            await reminders_repo.mark_canceled(session, reminder)
            continue
        if reminder.occurrence_start_at < now_utc - _STALE_AFTER:
            await reminders_repo.mark_sent(session, reminder, sent_at=now_utc)
            logger.warning(
                "Просроченное напоминание закрыто без отправки: id={}", reminder.id
            )
            continue

        settings_map = await settings_repo.get_all(session, user.id)
        if settings_map.get(SettingKey.REMINDERS_ENABLED.value, "on") != "on":
            await reminders_repo.mark_sent(session, reminder, sent_at=now_utc)
            continue

        allowed_at = quiet.next_allowed_moment(user, settings_map, now_utc=now_utc)
        if allowed_at > now_utc:
            # Тихий час или ручная тишина: не теряем напоминание, а откладываем.
            await postpone(session, reminder, until=allowed_at)
            continue

        tz = tz_for(user.tz)
        occurrence_local = reminder.occurrence_start_at.astimezone(tz)
        minutes_before = event.reminder_offset or 0
        text = build_reminder_text(
            title=event.title,
            minutes_before=minutes_before,
            start_local=occurrence_local,
            category=event.category,
        )
        ready.append(
            DueReminder(
                reminder=reminder,
                event=event,
                user=user,
                occurrence_local=occurrence_local,
                minutes_before=minutes_before,
                text=text,
            )
        )
    return ready


async def mark_sent(session: AsyncSession, reminder: Reminder, *, now_utc: datetime) -> None:
    """Помечает напоминание отправленным (вызывает джоб после успешной отправки)."""
    await reminders_repo.mark_sent(session, reminder, sent_at=now_utc)


async def reschedule_later(
    session: AsyncSession, reminder: Reminder, *, at: datetime
) -> Reminder:
    """Кнопка «Позже»: переносим напоминание на новое время."""
    reminder.status = ReminderStatus.PENDING
    reminder.send_at = at
    reminder.sent_at = None
    await session.flush()
    return reminder


#: Напоминание старше этого срока уже бессмысленно — закрываем без отправки.
_STALE_AFTER = timedelta(hours=2)


__all__ = [
    "DueReminder",
    "build_reminder_text",
    "collect_due",
    "mark_sent",
    "postpone",
    "reschedule_later",
]
