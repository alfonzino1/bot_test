"""Тесты повторяемости: правила, вхождения, переносы вхождений."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from chronos.constants import RepeatRule
from chronos.utils.recurrence import (
    build_rule,
    describe_rule,
    first_occurrence_after,
    next_occurrences,
    occurrences_between,
    parse_rule,
)

MOSCOW = ZoneInfo("Europe/Moscow")
MONDAY_10 = datetime(2026, 5, 11, 10, 0, tzinfo=MOSCOW)  # понедельник
DURATION = timedelta(hours=1)


@pytest.mark.parametrize(
    ("rule", "kind", "days"),
    [
        ("none", RepeatRule.NONE, frozenset()),
        ("daily", RepeatRule.DAILY, frozenset()),
        ("weekdays", RepeatRule.WEEKDAYS, frozenset()),
        ("weekly:MO,WE", RepeatRule.WEEKLY, frozenset({0, 2})),
        ("ерунда", RepeatRule.NONE, frozenset()),
    ],
)
def test_parse_rule(rule: str, kind: RepeatRule, days: frozenset[int]) -> None:
    spec = parse_rule(rule)
    assert spec.kind is kind
    assert spec.weekdays == days


def test_build_rule_round_trip() -> None:
    rule = build_rule(RepeatRule.WEEKLY, {2, 0})
    assert rule == "weekly:MO,WE"
    assert parse_rule(rule).weekdays == frozenset({0, 2})


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("daily", "каждый день"),
        ("weekdays", "по будням"),
        ("weekly:MO,WE", "по пн, ср"),
        ("none", ""),
    ],
)
def test_describe_rule(rule: str, expected: str) -> None:
    assert describe_rule(rule) == expected


def test_разовое_событие_даёт_одно_вхождение() -> None:
    window_start = MONDAY_10 - timedelta(hours=1)
    window_end = MONDAY_10 + timedelta(days=30)
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="none",
        window_start=window_start,
        window_end=window_end,
    )
    assert occurrences == [(MONDAY_10, MONDAY_10 + DURATION)]


def test_разовое_событие_вне_окна_не_попадает() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="none",
        window_start=MONDAY_10 + timedelta(days=2),
        window_end=MONDAY_10 + timedelta(days=3),
    )
    assert occurrences == []


def test_daily_даёт_по_вхождению_на_день() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="daily",
        window_start=datetime(2026, 5, 11, tzinfo=MOSCOW),
        window_end=datetime(2026, 5, 14, tzinfo=MOSCOW),
    )
    assert [start.date().isoformat() for start, _ in occurrences] == [
        "2026-05-11",
        "2026-05-12",
        "2026-05-13",
    ]


def test_weekdays_пропускает_выходные() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="weekdays",
        window_start=datetime(2026, 5, 11, tzinfo=MOSCOW),
        window_end=datetime(2026, 5, 18, tzinfo=MOSCOW),
    )
    weekdays = [start.weekday() for start, _ in occurrences]
    assert weekdays == [0, 1, 2, 3, 4]


def test_weekly_по_двум_дням() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="weekly:MO,WE",
        window_start=datetime(2026, 5, 11, tzinfo=MOSCOW),
        window_end=datetime(2026, 5, 21, tzinfo=MOSCOW),
    )
    assert [start.date().isoformat() for start, _ in occurrences] == [
        "2026-05-11",
        "2026-05-13",
        "2026-05-18",
        "2026-05-20",
    ]


def test_исключения_подавляют_вхождение() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="daily",
        window_start=datetime(2026, 5, 11, tzinfo=MOSCOW),
        window_end=datetime(2026, 5, 14, tzinfo=MOSCOW),
        exceptions=("2026-05-12",),
    )
    assert [start.date().isoformat() for start, _ in occurrences] == [
        "2026-05-11",
        "2026-05-13",
    ]


def test_окно_не_начинает_серию_раньше_якоря() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="daily",
        window_start=datetime(2026, 5, 9, tzinfo=MOSCOW),  # до якоря
        window_end=datetime(2026, 5, 13, tzinfo=MOSCOW),
    )
    assert [start.date().isoformat() for start, _ in occurrences] == [
        "2026-05-11",
        "2026-05-12",
    ]


def test_next_occurrences_и_первое_после() -> None:
    after = MONDAY_10 + timedelta(hours=2)  # уже после начала вхождения
    found = next_occurrences(
        anchor_start=MONDAY_10,
        duration=DURATION,
        rule="daily",
        after=after,
        count=2,
    )
    assert [start.date().isoformat() for start, _ in found] == ["2026-05-12", "2026-05-13"]

    first = first_occurrence_after(
        anchor_start=MONDAY_10, duration=DURATION, rule="none", after=after
    )
    assert first is None  # разовое событие уже прошло


def test_длительность_сохраняется_во_всех_вхождениях() -> None:
    occurrences = occurrences_between(
        anchor_start=MONDAY_10,
        duration=timedelta(minutes=90),
        rule="daily",
        window_start=MONDAY_10,
        window_end=MONDAY_10 + timedelta(days=1),
    )
    for start, end in occurrences:
        assert end - start == timedelta(minutes=90)
