"""Тесты аналитики: разрезы, план vs факт, пики, тренды (ТЗ, раздел 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from chronos.constants import EventStatus
from chronos.services import analytics
from chronos.services.analytics import PeriodKind

MOSCOW = ZoneInfo("Europe/Moscow")
NOW_LOCAL = datetime(2026, 5, 12, 10, 30, tzinfo=MOSCOW)
NOW_UTC = NOW_LOCAL.astimezone(UTC)


@dataclass
class FakeLog:
    """Запись времени для аналитики (структурный тип LogLike)."""

    category: str
    start_at: datetime
    end_at: datetime | None = None


@dataclass
class FakeEvent:
    """Событие расписания для аналитики (структурный тип EventLike)."""

    id: int
    title: str
    start_at: datetime
    end_at: datetime
    repeat_rule: str = "none"
    category: str | None = None
    status: EventStatus = EventStatus.PLANNED
    exceptions: list[str] = field(default_factory=list)


def _log(day: int, hour: int, minutes: int, category: str = "work") -> FakeLog:
    start = datetime(2026, 5, day, hour, 0, tzinfo=MOSCOW)
    return FakeLog(category=category, start_at=start, end_at=start + timedelta(minutes=minutes))


def test_границы_периодов() -> None:
    day_start, day_end = analytics.period_bounds(PeriodKind.DAY, NOW_LOCAL)
    assert (day_start.date(), day_end.date()) == (date(2026, 5, 12), date(2026, 5, 13))

    week_start, week_end = analytics.period_bounds(PeriodKind.WEEK, NOW_LOCAL)
    assert week_start.date() == date(2026, 5, 11)  # понедельник
    assert week_end.date() == date(2026, 5, 18)

    month_start, month_end = analytics.period_bounds(PeriodKind.MONTH, NOW_LOCAL)
    assert (month_start.date(), month_end.date()) == (date(2026, 5, 1), date(2026, 6, 1))


def test_предыдущий_период() -> None:
    start, end = analytics.period_bounds(PeriodKind.DAY, NOW_LOCAL)
    prev_start, prev_end = analytics.previous_bounds(PeriodKind.DAY, start, end)
    assert prev_start.date() == date(2026, 5, 11)
    assert prev_end == start


def test_запись_через_полночь_режется_на_два_отрезка() -> None:
    log = FakeLog(
        category="work",
        start_at=datetime(2026, 5, 12, 23, 30, tzinfo=MOSCOW),
        end_at=datetime(2026, 5, 13, 0, 30, tzinfo=MOSCOW),
    )
    segments = analytics.split_log(log, tz=MOSCOW, now_utc=NOW_UTC)
    assert len(segments) == 2
    assert segments[0].start_local.date() == date(2026, 5, 12)
    assert segments[1].end_local.date() == date(2026, 5, 13)
    assert analytics.total_minutes(segments) == 60


def test_незакрытая_запись_считается_до_сейчас() -> None:
    log = FakeLog(
        category="study", start_at=datetime(2026, 5, 12, 9, 30, tzinfo=MOSCOW), end_at=None
    )
    segments = analytics.split_log(log, tz=MOSCOW, now_utc=NOW_UTC)
    assert analytics.total_minutes(segments) == 60


def test_фокус_только_по_фокусным_категориям() -> None:
    logs = [
        _log(12, 9, 60, "work"),
        _log(12, 10, 30, "study"),
        _log(12, 11, 120, "social"),
        _log(12, 13, 30, "sport"),
    ]
    report = analytics.build_report(
        period=PeriodKind.DAY, now_local=NOW_LOCAL, logs=logs, now_utc=NOW_UTC
    )
    assert report.total_minutes == 240
    assert report.focus_minutes == 90  # работа + учёба
    assert report.category_minutes("social") == 120


def test_план_vs_факт_по_категориям() -> None:
    events = [
        FakeEvent(
            id=1,
            title="Созвон",
            start_at=datetime(2026, 5, 12, 11, 0, tzinfo=MOSCOW),
            end_at=datetime(2026, 5, 12, 12, 0, tzinfo=MOSCOW),
            category="work",
        )
    ]
    logs = [_log(12, 11, 90, "work")]
    report = analytics.build_report(
        period=PeriodKind.DAY,
        now_local=NOW_LOCAL,
        logs=logs,
        events=events,
        now_utc=NOW_UTC,
    )
    assert report.planned_minutes == 60
    assert report.events_planned == 1
    row = report.plan_vs_fact[0]
    assert (row.category, row.planned_minutes, row.actual_minutes) == ("work", 60, 90)
    assert row.delta_minutes == 30


def test_отменённые_события_не_входят_в_план() -> None:
    events = [
        FakeEvent(
            id=1,
            title="Отменённый созвон",
            start_at=datetime(2026, 5, 12, 11, 0, tzinfo=MOSCOW),
            end_at=datetime(2026, 5, 12, 12, 0, tzinfo=MOSCOW),
            category="work",
            status=EventStatus.CANCELED,
        )
    ]
    report = analytics.build_report(
        period=PeriodKind.DAY,
        now_local=NOW_LOCAL,
        logs=[],
        events=events,
        now_utc=NOW_UTC,
    )
    assert report.planned_minutes == 0
    assert report.empty is True


def test_повторяющееся_событие_даёт_план_на_каждый_день() -> None:
    events = [
        FakeEvent(
            id=1,
            title="Зал",
            start_at=datetime(2026, 5, 11, 7, 30, tzinfo=MOSCOW),
            end_at=datetime(2026, 5, 11, 8, 30, tzinfo=MOSCOW),
            repeat_rule="weekdays",
            category="sport",
        )
    ]
    report = analytics.build_report(
        period=PeriodKind.WEEK,
        now_local=NOW_LOCAL,
        logs=[],
        events=events,
        now_utc=NOW_UTC,
    )
    assert report.planned_minutes == 5 * 60  # пн–пт
    assert report.events_planned == 5


def test_пики_продуктивности_по_часам() -> None:
    logs = [
        _log(12, 9, 30, "work"),
        _log(12, 10, 60, "work"),
        _log(12, 15, 15, "work"),
    ]
    report = analytics.build_report(
        period=PeriodKind.DAY, now_local=NOW_LOCAL, logs=logs, now_utc=NOW_UTC
    )
    assert [bucket.hour for bucket in report.peaks] == [10, 9, 15]
    assert report.peaks[0].focus_minutes == 60


def test_тренд_сравнивает_с_прошлым_периодом() -> None:
    logs = [_log(12, 9, 120, "work")]
    previous = [_log(11, 9, 60, "work")]
    report = analytics.build_report(
        period=PeriodKind.DAY,
        now_local=NOW_LOCAL,
        logs=logs,
        previous_logs=previous,
        now_utc=NOW_UTC,
    )
    assert report.trend is not None
    assert report.trend.direction is analytics.Direction.UP
    assert report.trend.delta_minutes == 60
    assert report.trend.delta_percent == 100


def test_тренд_без_прошлого_периода_не_строится() -> None:
    report = analytics.build_report(
        period=PeriodKind.DAY,
        now_local=NOW_LOCAL,
        logs=[_log(12, 9, 30, "work")],
        now_utc=NOW_UTC,
    )
    assert report.trend is None


def test_разрез_по_категориям_сортирован_по_минутам() -> None:
    logs = [_log(12, 9, 30, "social"), _log(12, 10, 90, "work")]
    report = analytics.build_report(
        period=PeriodKind.DAY, now_local=NOW_LOCAL, logs=logs, now_utc=NOW_UTC
    )
    assert [row.category for row in report.by_category] == ["work", "social"]
    assert report.by_category[0].is_focus is True
    assert report.by_category[1].is_focus is False
    assert report.focus_share == 0.75


def test_категория_без_плана_попадает_в_разрез() -> None:
    events = [
        FakeEvent(
            id=1,
            title="Без метки",
            start_at=datetime(2026, 5, 12, 11, 0, tzinfo=MOSCOW),
            end_at=datetime(2026, 5, 12, 12, 0, tzinfo=MOSCOW),
            category=None,
        )
    ]
    report = analytics.build_report(
        period=PeriodKind.DAY,
        now_local=NOW_LOCAL,
        logs=[],
        events=events,
        now_utc=NOW_UTC,
    )
    assert report.plan_vs_fact[0].category is None
    assert report.planned_minutes == 60
