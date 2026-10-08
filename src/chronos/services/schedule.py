"""Сервис расписания: создание, перенос, вхождения и материализация напоминаний.

Здесь живёт «склейка» модуля A: после создания или переноса события сервис сам
приводит напоминания в согласованное состояние.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import (
    DEFAULT_EVENT_MINUTES,
    EventStatus,
    RepeatRule,
)
from chronos.logging_setup import logger
from chronos.models import ScheduleEvent, User
from chronos.repositories import reminders as reminders_repo
from chronos.repositories import schedule as schedule_repo
from chronos.utils.recurrence import next_occurrences, occurrences_between, parse_rule
from chronos.utils.timezones import day_bounds_local, tz_for, to_utc


@dataclass(frozen=True, slots=True)
class Occurrence:
    """Конкретное вхождение события: то, что видит пользователь в списке."""

    event_id: int
    title: str
    category: str | None
    status: EventStatus
    repeat_rule: str
    reminder_offset: int | None
    start_local: datetime
    end_local: datetime
    #: Локальная дата вхождения — ключ переноса и подавления (D-07).
    occurrence_date: date

    @property
    def start_utc(self) -> datetime:
        return to_utc(self.start_local)

    @property
    def end_utc(self) -> datetime:
        return to_utc(self.end_local)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_local - self.start_local).total_seconds() // 60)

    @property
    def is_recurring(self) -> bool:
        return self.repeat_rule != RepeatRule.NONE.value


def user_zone(user: User):
    """Зона пользователя (короткий помощник для читаемости)."""
    return tz_for(user.tz)


def expand_event(
    event: ScheduleEvent,
    *,
    tz,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Вхождения события в локальном окне (с учётом переносов и статуса).

    Отменённые и перенесённые события в план не входят, но возвращаются:
    список «Сегодня» показывает их со статусом (docs/DECISIONS.md D-10).
    """
    anchor_local = event.start_at.astimezone(tz)
    end_local = event.end_at.astimezone(tz)
    duration = end_local - anchor_local
    return occurrences_between(
        anchor_start=anchor_local,
        duration=duration,
        rule=event.repeat_rule,
        window_start=window_start,
        window_end=window_end,
        exceptions=event.exceptions or (),
    )


def occurrences_of(
    event: ScheduleEvent,
    *,
    tz,
    window_start: datetime,
    window_end: datetime,
) -> list[Occurrence]:
    """Обёртка ``expand_event`` в доменный тип ``Occurrence``."""
    result: list[Occurrence] = []
    for start_local, end_local in expand_event(
        event, tz=tz, window_start=window_start, window_end=window_end
    ):
        result.append(
            Occurrence(
                event_id=event.id,
                title=event.title,
                category=event.category,
                status=EventStatus(event.status),
                repeat_rule=event.repeat_rule,
                reminder_offset=event.reminder_offset,
                start_local=start_local,
                end_local=end_local,
                occurrence_date=start_local.date(),
            )
        )
    return result


async def create(
    session: AsyncSession,
    user: User,
    *,
    title: str,
    start_local: datetime,
    end_local: datetime | None = None,
    repeat_rule: str = RepeatRule.NONE.value,
    category: str | None = None,
    reminder_offset: int | None = None,
    now_utc: datetime,
    horizon_days: int = 7,
) -> ScheduleEvent:
    """Создаёт событие и напоминания к нему.

    Для повторяющихся событий «якорь» сдвигается вперёд: если пользователь
    добавил «зал по будням в 7:30» после 7:30, первый день — следующий будний.
    """
    tz = user_zone(user)
    if start_local.tzinfo is None:
        raise ValueError("start_local должен быть aware в зоне пользователя")
    if end_local is None:
        end_local = start_local + timedelta(minutes=DEFAULT_EVENT_MINUTES)
    if end_local <= start_local:
        raise ValueError("Конец события должен быть позже начала")

    now_local = now_utc.astimezone(tz)
    if parse_rule(repeat_rule).is_recurring and start_local < now_local:
        upcoming = next_occurrences(
            anchor_start=start_local,
            duration=end_local - start_local,
            rule=repeat_rule,
            after=now_local,
            count=1,
        )
        if upcoming:
            start_local, end_local = upcoming[0]

    event = await schedule_repo.create_event(
        session,
        user_id=user.id,
        title=title.strip()[:200],
        start_at=to_utc(start_local),
        end_at=to_utc(end_local),
        repeat_rule=repeat_rule,
        category=category,
        reminder_offset=reminder_offset,
    )
    await ensure_reminders(session, user, now_utc=now_utc, horizon_days=horizon_days)
    logger.info(
        "Создано событие: id={} user_id={} start={} rule={}",
        event.id,
        user.id,
        event.start_at.isoformat(),
        event.repeat_rule,
    )
    return event


async def delete(session: AsyncSession, user: User, event: ScheduleEvent) -> None:
    """Удаляет событие вместе с его напоминаниями."""
    await schedule_repo.delete_event(session, event)
    logger.info("Удалено событие: id={} user_id={}", event.id, user.id)


async def set_status(
    session: AsyncSession,
    user: User,
    event: ScheduleEvent,
    status: EventStatus,
    *,
    now_utc: datetime,
) -> ScheduleEvent:
    """Меняет статус и отменяет лишние напоминания.

    «✅ Иду» и «⏰ Опоздаю» напоминание сохраняют, «❌ Отменяю» — убирают.
    """
    await schedule_repo.set_status(session, event, status)
    if status is EventStatus.CANCELED:
        canceled = await reminders_repo.cancel_future_for_event(session, event.id, after=now_utc)
        logger.info("Событие отменено: id={} отменено напоминаний={}", event.id, canceled)
    elif status is EventStatus.PLANNED:
        await ensure_reminders(session, user, now_utc=now_utc)
    return event


async def move_occurrence(
    session: AsyncSession,
    user: User,
    event: ScheduleEvent,
    occurrence: Occurrence,
    *,
    new_start_local: datetime,
    new_end_local: datetime | None = None,
    now_utc: datetime,
    horizon_days: int = 7,
) -> ScheduleEvent:
    """Переносит одно вхождение.

    Разовое событие просто меняет время. Для серии: дата вхождения попадает в
    ``exceptions`` (вхождение подавляется), напоминание этого вхождения
    отменяется, а на новое время создаётся разовое событие — серия, её статус и
    напоминания остальных вхождений не трогаются (docs/DECISIONS.md D-07).
    """
    duration = timedelta(minutes=occurrence.duration_minutes)
    if new_end_local is None:
        new_end_local = new_start_local + duration

    if not event.is_recurring:
        updated = await schedule_repo.set_times(
            session, event, start_at=to_utc(new_start_local), end_at=to_utc(new_end_local)
        )
        await reminders_repo.cancel_future_for_event(session, event.id, after=now_utc)
        await ensure_reminders(session, user, now_utc=now_utc, horizon_days=horizon_days)
        return updated

    await schedule_repo.add_exception(session, event, occurrence.occurrence_date.isoformat())
    await reminders_repo.cancel_for_occurrence(session, event.id, occurrence.start_utc)
    moved = await create(
        session,
        user,
        title=event.title,
        start_local=new_start_local,
        end_local=new_end_local,
        repeat_rule=RepeatRule.NONE.value,
        category=event.category,
        reminder_offset=event.reminder_offset,
        now_utc=now_utc,
        horizon_days=horizon_days,
    )
    logger.info(
        "Перенесено вхождение: event_id={} {} → {} (разовое событие id={})",
        event.id,
        occurrence.occurrence_date.isoformat(),
        new_start_local.isoformat(),
        moved.id,
    )
    return moved


async def occurrences_for_window(
    session: AsyncSession,
    user: User,
    *,
    window_start_local: datetime,
    window_end_local: datetime,
) -> list[Occurrence]:
    """Все вхождения (включая серии) в локальном окне, отсортированные по времени."""
    tz = user_zone(user)
    events = await schedule_repo.list_for_window(
        session, user.id, to_utc(window_start_local), to_utc(window_end_local)
    )
    result: list[Occurrence] = []
    for event in events:
        result.extend(
            occurrences_of(
                event, tz=tz, window_start=window_start_local, window_end=window_end_local
            )
        )
    result.sort(key=lambda item: item.start_local)
    return result


async def day_occurrences(
    session: AsyncSession, user: User, *, day: date
) -> list[Occurrence]:
    """Расписание на конкретный локальный день."""
    start, end = day_bounds_local(day, user_zone(user))
    return await occurrences_for_window(
        session, user, window_start_local=start, window_end_local=end
    )


async def week_occurrences(
    session: AsyncSession, user: User, *, start_day: date, days: int = 7
) -> dict[date, list[Occurrence]]:
    """Расписание на N дней, сгруппированное по датам (для экрана «Расписание»)."""
    tz = user_zone(user)
    window_start, _ = day_bounds_local(start_day, tz)
    _, window_end = day_bounds_local(start_day + timedelta(days=days - 1), tz)
    occurrences = await occurrences_for_window(
        session, user, window_start_local=window_start, window_end_local=window_end
    )
    grouped: dict[date, list[Occurrence]] = {
        start_day + timedelta(days=offset): [] for offset in range(days)
    }
    for occurrence in occurrences:
        grouped.setdefault(occurrence.occurrence_date, []).append(occurrence)
    return grouped


async def upcoming(
    session: AsyncSession, user: User, *, now_utc: datetime, within: timedelta
) -> Occurrence | None:
    """Ближайшее вхождение в пределах ``within`` (нужно напоминаниям и опросам)."""
    tz = user_zone(user)
    now_local = now_utc.astimezone(tz)
    occurrences = await occurrences_for_window(
        session, user, window_start_local=now_local, window_end_local=now_local + within
    )
    for occurrence in occurrences:
        if occurrence.status in (EventStatus.CANCELED, EventStatus.MOVED):
            continue
        if occurrence.start_local >= now_local:
            return occurrence
    return None


async def current_occurrence(
    session: AsyncSession, user: User, *, now_utc: datetime
) -> Occurrence | None:
    """Событие, которое идёт прямо сейчас по плану (для контекстного опроса)."""
    tz = user_zone(user)
    now_local = now_utc.astimezone(tz)
    occurrences = await occurrences_for_window(
        session,
        user,
        window_start_local=now_local - timedelta(days=1),
        window_end_local=now_local,
    )
    for occurrence in occurrences:
        if occurrence.status in (EventStatus.CANCELED, EventStatus.MOVED):
            continue
        if occurrence.start_local <= now_local < occurrence.end_local:
            return occurrence
    return None


async def ensure_reminders(
    session: AsyncSession,
    user: User,
    *,
    now_utc: datetime,
    horizon_days: int = 7,
) -> int:
    """Материализует напоминания на горизонт вперёд. Идемпотентно.

    Возвращает количество созданных/существующих напоминаний — полезно в тестах.
    """
    tz = user_zone(user)
    now_local = now_utc.astimezone(tz)
    horizon_end_local = now_local + timedelta(days=horizon_days)
    events = await schedule_repo.list_with_reminders(
        session, horizon_end=to_utc(horizon_end_local), user_id=user.id
    )
    created = 0
    for event in events:
        if event.reminder_offset is None:
            continue
        for start_local, _ in expand_event(
            event, tz=tz, window_start=now_local, window_end=horizon_end_local
        ):
            send_local = start_local - timedelta(minutes=event.reminder_offset)
            if send_local < now_local:
                continue
            await reminders_repo.ensure_pending(
                session,
                user_id=user.id,
                schedule_id=event.id,
                occurrence_start_at=to_utc(start_local),
                send_at=to_utc(send_local),
            )
            created += 1
    return created


async def day_focus_plan_minutes(
    session: AsyncSession, user: User, *, day: date
) -> int:
    """Сколько минут событий запланировано на день (для меню)."""
    start, end = day_bounds_local(day, user_zone(user))
    occurrences = await occurrences_for_window(
        session, user, window_start_local=start, window_end_local=end
    )
    return sum(
        occurrence.duration_minutes
        for occurrence in occurrences
        if occurrence.status.counts_as_plan
    )


__all__ = [
    "Occurrence",
    "create",
    "current_occurrence",
    "day_focus_plan_minutes",
    "day_occurrences",
    "delete",
    "ensure_reminders",
    "expand_event",
    "move_occurrence",
    "occurrences_for_window",
    "occurrences_of",
    "set_status",
    "upcoming",
    "user_zone",
    "week_occurrences",
]
