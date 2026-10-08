"""Тесты парсера дат и времени (ТЗ, раздел 9: юнит-тесты для парсера)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from chronos.utils.datetime_parser import (
    parse_date_text,
    parse_duration_text,
    parse_event_text,
    parse_interval_text,
    parse_time_range_text,
    parse_time_text,
)

MOSCOW = ZoneInfo("Europe/Moscow")
#: Вторник, 12 мая 2026, 10:30 по Москве.
NOW = datetime(2026, 5, 12, 10, 30, tzinfo=MOSCOW)


def test_quick_add_разбирает_полную_строку() -> None:
    draft = parse_event_text("Встреча завтра 15:00-16:00 #работа", now_local=NOW)
    assert draft.title == "Встреча"
    assert draft.date_local == date(2026, 5, 13)
    assert draft.start_local == datetime(2026, 5, 13, 15, 0, tzinfo=MOSCOW)
    assert draft.end_local == datetime(2026, 5, 13, 16, 0, tzinfo=MOSCOW)
    assert draft.category == "work"
    assert draft.reminder_offset == 15  # напоминание по умолчанию
    assert draft.missing == ()


def test_висячий_предлог_не_попадает_в_название() -> None:
    assert parse_event_text("Созвон в 18:00", now_local=NOW).title == "Созвон"
    assert parse_event_text("Стендап в пн 9:45-10:00", now_local=NOW).title == "Стендап"


def test_время_в_прошлом_переносится_на_завтра() -> None:
    draft = parse_event_text("Зарядка 09:00", now_local=NOW)
    assert draft.start_local == datetime(2026, 5, 13, 9, 0, tzinfo=MOSCOW)


def test_явная_дата_сегодня_сохраняет_прошлое_время() -> None:
    draft = parse_event_text("Созвон сегодня 09:00", now_local=NOW)
    assert draft.start_local == datetime(2026, 5, 12, 9, 0, tzinfo=MOSCOW)


def test_день_недели_даёт_ближайшее_будущее() -> None:
    draft = parse_event_text("Стендап в понедельник 9:45-10:00", now_local=NOW)
    assert draft.date_local == date(2026, 5, 18)  # следующий понедельник


def test_повтор_по_будням() -> None:
    draft = parse_event_text("Зал по будням 7:30", now_local=NOW)
    assert draft.repeat_rule == "weekdays"
    assert draft.start_local == datetime(2026, 5, 13, 7, 30, tzinfo=MOSCOW)


def test_повтор_каждый_день_и_категория() -> None:
    draft = parse_event_text("Учёба каждый день 9:00-10:30 #учёба", now_local=NOW)
    assert draft.repeat_rule == "daily"
    assert draft.category == "study"
    assert draft.title == "Учёба"


def test_относительное_смещение_через_часы() -> None:
    draft = parse_event_text("Почитать через 2 часа #отдых", now_local=NOW)
    assert draft.start_local == datetime(2026, 5, 12, 12, 30, tzinfo=MOSCOW)
    assert draft.category == "rest"


def test_относительное_смещение_через_дни() -> None:
    draft = parse_event_text("Отчёт через 3 дня 12:00", now_local=NOW)
    assert draft.date_local == date(2026, 5, 15)


def test_дата_точками() -> None:
    draft = parse_event_text("Врач 01.06 12:30", now_local=NOW)
    assert draft.date_local == date(2026, 6, 1)


def test_время_точкой_не_путается_с_датой() -> None:
    draft = parse_event_text("Йога 15.30", now_local=NOW)
    assert draft.date_local == date(2026, 5, 12)
    assert draft.start_local == datetime(2026, 5, 12, 15, 30, tzinfo=MOSCOW)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Врач 01.06 12:30 без напоминания", None),
        ("Врач 01.06 12:30 не напоминай", None),
        ("Врач 01.06 12:30 в момент", 0),
        ("Врач 01.06 12:30 за 15 мин", 15),
        ("Врач 01.06 12:30 за час", 60),
    ],
)
def test_напоминания(text: str, expected: int | None) -> None:
    draft = parse_event_text(text, now_local=NOW)
    assert draft.reminder_offset == expected
    assert draft.title == "Врач"


def test_часть_суток_как_время() -> None:
    assert parse_event_text("Купить продукты вечером", now_local=NOW).start_local == datetime(
        2026, 5, 12, 19, 0, tzinfo=MOSCOW
    )
    # «утром» (9:00) уже прошло — правило «не тупи» переносит на завтра
    assert parse_event_text("Пробежка утром", now_local=NOW).start_local == datetime(
        2026, 5, 13, 9, 0, tzinfo=MOSCOW
    )


def test_своя_метка_сохраняется_как_категория() -> None:
    draft = parse_event_text("Медитация #йога 20:00", now_local=NOW)
    assert draft.category == "йога"
    assert draft.category_custom_label == "йога"


def test_не_понял_когда_нет_названия() -> None:
    draft = parse_event_text("15:30", now_local=NOW)
    assert draft.title == ""
    assert "title" in draft.missing


def test_не_понял_когда_нет_времени() -> None:
    draft = parse_event_text("Позвонить маме завтра", now_local=NOW)
    assert draft.title == "Позвонить маме"
    assert draft.date_local == date(2026, 5, 13)
    assert draft.start_local is None
    assert "time" in draft.missing


def test_пустой_ввод() -> None:
    draft = parse_event_text("   ", now_local=NOW)
    assert draft.missing == ("title", "time")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("9:30-18:00", (time(9, 30), time(18, 0))),
        ("с 9 до 18", (time(9, 0), time(18, 0))),
        ("23:00-8:00", (time(23, 0), time(8, 0))),
        ("ерунда", None),
    ],
)
def test_интервалы(text: str, expected: tuple[time, time] | None) -> None:
    assert parse_interval_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2h", timedelta(hours=2)),
        ("2ч", timedelta(hours=2)),
        ("30m", timedelta(minutes=30)),
        ("45 минут", timedelta(minutes=45)),
        ("2 часа 30 минут", timedelta(hours=2, minutes=30)),
        ("ерунда", None),
    ],
)
def test_длительности(text: str, expected: timedelta | None) -> None:
    assert parse_duration_text(text) == expected


def test_разбор_даты_текстом() -> None:
    assert parse_date_text("завтра", now_local=NOW) == date(2026, 5, 13)
    assert parse_date_text("через 3 дня", now_local=NOW) == date(2026, 5, 15)
    assert parse_date_text("12.05", now_local=NOW) == date(2026, 5, 12)
    assert parse_date_text("2026-06-01", now_local=NOW) == date(2026, 6, 1)
    assert parse_date_text("пт", now_local=NOW) == date(2026, 5, 15)
    assert parse_date_text("ерунда", now_local=NOW) is None


def test_разбор_времени_и_диапазона() -> None:
    assert parse_time_text("в 15:00", on_date=date(2026, 5, 12), now_local=NOW) == datetime(
        2026, 5, 12, 15, 0, tzinfo=MOSCOW
    )
    interval = parse_time_range_text(
        "22:00-01:00", on_date=date(2026, 5, 12), now_local=NOW
    )
    assert interval is not None
    start, end = interval
    assert end - start == timedelta(hours=3)  # интервал через полночь
    assert parse_time_range_text("ерунда", on_date=date(2026, 5, 12), now_local=NOW) is None
