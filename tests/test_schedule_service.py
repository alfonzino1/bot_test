"""Тесты сервиса расписания: создание, вхождения, напоминания, переносы.

ТЗ, раздел 9: логика планирования должна быть покрыта тестами. Здесь проверяем
связку «расписание → напоминания», которая и есть ключевая фишка бота.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import EventStatus, RepeatRule
from chronos.models import User
from chronos.repositories import reminders as reminders_repo
from chronos.repositories import schedule as schedule_repo
from chronos.services import schedule as schedule_service
from chronos.utils.db import Database
from chronos.utils.recurrence import build_rule

MOSCOW = ZoneInfo("Europe/Moscow")
#: Вторник, 12 мая 2026, 10:30 по Москве.
NOW_UTC = datetime(2026, 5, 12, 7, 30, tzinfo=UTC)


def _msk(day: int, hour: int, minute: int = 0, *, month: int = 5) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=MOSCOW)


async def test_разовое_событие_материализует_напоминание(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=_msk(13, 15),
            end_local=_msk(13, 16),
            category="work",
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
    assert len(reminders) == 1
    # 15:00 МСК минус 15 минут = 14:45 МСК = 11:45 UTC
    assert reminders[0].send_at == datetime(2026, 5, 13, 11, 45, tzinfo=UTC)


async def test_напоминания_материализуются_идемпотентно(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Зал",
            start_local=_msk(13, 7, 30),
            end_local=_msk(13, 8, 30),
            repeat_rule=RepeatRule.DAILY.value,
            reminder_offset=15,
            now_utc=NOW_UTC,
            horizon_days=3,
        )
        first = await reminders_repo.list_for_event(session, event.id)
        await schedule_service.ensure_reminders(session, user, now_utc=NOW_UTC, horizon_days=3)
        await schedule_service.ensure_reminders(session, user, now_utc=NOW_UTC, horizon_days=3)
        second = await reminders_repo.list_for_event(session, event.id)
    assert len(first) == len(second) == 3
    assert len({reminder.occurrence_start_at for reminder in second}) == 3


async def test_событие_без_напоминания_не_создаёт_записей(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Тишина",
            start_local=_msk(13, 12),
            reminder_offset=None,
            now_utc=NOW_UTC,
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
    assert reminders == []


async def test_повторяющееся_событие_в_прошлом_сдвигается_вперёд(
    database: Database, user: User
) -> None:
    """«Зал по будням в 7:30» после 7:30 ⇒ первый день — следующий будний."""
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Зал",
            start_local=_msk(12, 7, 30),  # сегодня, но время уже прошло
            end_local=_msk(12, 8, 30),
            repeat_rule=RepeatRule.WEEKDAYS.value,
            reminder_offset=None,
            now_utc=NOW_UTC,
        )
    assert event.start_at.astimezone(MOSCOW).date().isoformat() == "2026-05-13"


async def test_вхождения_на_день_учитывают_серии(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        await schedule_service.create(
            session,
            user,
            title="Учёба",
            start_local=_msk(13, 9),
            end_local=_msk(13, 10),
            repeat_rule=build_rule(RepeatRule.WEEKLY, {2}),  # среда
            reminder_offset=None,
            now_utc=NOW_UTC,
        )
    async with database.session() as session:
        wednesday = await schedule_service.day_occurrences(session, user, day=_msk(20, 0).date())
        tuesday = await schedule_service.day_occurrences(session, user, day=_msk(19, 0).date())
    assert [item.title for item in wednesday] == ["Учёба"]
    assert tuesday == []


async def test_перенос_вхождения_серии_не_ломает_серию(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        series = await schedule_service.create(
            session,
            user,
            title="Зал",
            start_local=_msk(11, 7, 30),  # понедельник
            end_local=_msk(11, 8, 30),
            repeat_rule=build_rule(RepeatRule.WEEKLY, {0}),
            category="sport",
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        # Якорь сдвинулся на ближайший понедельник 18 мая
        monday_occurrence = (
            await schedule_service.day_occurrences(session, user, day=_msk(18, 0).date())
        )[0]
        moved = await schedule_service.move_occurrence(
            session,
            user,
            series,
            monday_occurrence,
            new_start_local=_msk(19, 8, 0),
            now_utc=NOW_UTC,
        )
        monday_after = await schedule_service.day_occurrences(
            session, user, day=_msk(18, 0).date()
        )
        tuesday_after = await schedule_service.day_occurrences(
            session, user, day=_msk(19, 0).date()
        )
        next_monday = await schedule_service.day_occurrences(
            session, user, day=_msk(25, 0).date()
        )

    assert "2026-05-18" in series.exceptions
    assert monday_after == []  # вхождение подавлено
    assert [item.title for item in tuesday_after] == ["Зал"]  # разовое на новое время
    assert moved.id != series.id
    assert series.status is not EventStatus.MOVED  # серия осталась активной
    assert [item.title for item in next_monday] == ["Зал"]  # следующие недели живы


async def test_отмена_события_отменяет_напоминания(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=_msk(13, 15),
            end_local=_msk(13, 16),
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        await schedule_service.set_status(
            session, user, event, EventStatus.CANCELED, now_utc=NOW_UTC
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
    assert reminders[0].status.value == "canceled"


async def test_статус_иду_сохраняет_напоминание(database: Database, user: User) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=_msk(13, 15),
            end_local=_msk(13, 16),
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        await schedule_service.set_status(
            session, user, event, EventStatus.GOING, now_utc=NOW_UTC
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
    assert reminders[0].status.value == "pending"


async def test_удаление_события_убирает_напоминания(
    database: Database, user: User
) -> None:
    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=_msk(13, 15),
            end_local=_msk(13, 16),
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        await schedule_service.delete(session, user, event)
        reminders = await reminders_repo.list_for_event(session, event.id)
        events = await schedule_repo.list_for_window(
            session, user.id, NOW_UTC, NOW_UTC + timedelta(days=30)
        )
    assert reminders == []
    assert events == []


async def test_ближайшее_событие_и_текущее(database: Database, user: User) -> None:
    async with database.session() as session:
        await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=_msk(12, 10),  # идёт прямо сейчас (10:30 МСК)
            end_local=_msk(12, 11),
            reminder_offset=None,
            now_utc=NOW_UTC,
        )
        await schedule_service.create(
            session,
            user,
            title="Обед",
            start_local=_msk(12, 13),
            end_local=_msk(12, 14),
            reminder_offset=None,
            now_utc=NOW_UTC,
        )
        current = await schedule_service.current_occurrence(session, user, now_utc=NOW_UTC)
        upcoming = await schedule_service.upcoming(
            session, user, now_utc=NOW_UTC, within=timedelta(hours=4)
        )
    assert current is not None and current.title == "Созвон"
    assert upcoming is not None and upcoming.title == "Обед"


async def test_некорректный_интервал_отклоняется(database: Database, user: User) -> None:
    async with database.session() as session:
        with pytest.raises(ValueError):
            await schedule_service.create(
                session,
                user,
                title="Кривое",
                start_local=_msk(13, 16),
                end_local=_msk(13, 15),
                now_utc=NOW_UTC,
            )
