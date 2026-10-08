"""Аналитика (модуль C): отчёты по периодам, план vs факт, тренды, пики.

Модуль работает на структурных типах (``LogLike``/``EventLike``), поэтому его
можно тестировать без БД и без ORM: в тестах достаточно простых объектов
с нужными атрибутами.

Ключевые правила:

* «фокус» — только фокусные категории (docs/DECISIONS.md D-03);
* план — минуты событий расписания без отменённых (docs/DECISIONS.md D-10);
* записи разрезаются по локальной полуночи: сессия через ночь не «переезжает»
  целиком в один день.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from chronos.constants import (
    CATEGORY_ORDER,
    EventStatus,
    is_focus_category,
)
from chronos.utils.recurrence import occurrences_between
from chronos.utils.timezones import day_bounds_local


class PeriodKind(StrEnum):
    """Период отчёта."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class Direction(StrEnum):
    """Направление тренда (без оценок — только факт)."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


class LogLike(Protocol):
    """Запись времени — всё, что нужно аналитике."""

    category: str
    start_at: datetime
    end_at: datetime | None


class EventLike(Protocol):
    """Событие расписания — всё, что нужно аналитике для «плана»."""

    id: int
    title: str
    start_at: datetime
    end_at: datetime
    repeat_rule: str
    category: str | None
    status: EventStatus
    exceptions: list[str]


@dataclass(frozen=True, slots=True)
class Segment:
    """Отрезок записи времени, не пересекающий локальную полночь."""

    category: str
    start_local: datetime
    end_local: datetime

    @property
    def seconds(self) -> float:
        return max(0.0, (self.end_local - self.start_local).total_seconds())


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    """Итог по категории: минуты и доля от общего времени."""

    category: str | None
    minutes: int
    share: float
    is_focus: bool


@dataclass(frozen=True, slots=True)
class PlanVsFactRow:
    """Строка «план vs факт» по категории."""

    category: str | None
    planned_minutes: int
    actual_minutes: int

    @property
    def delta_minutes(self) -> int:
        return self.actual_minutes - self.planned_minutes


@dataclass(frozen=True, slots=True)
class HourBucket:
    """Час суток и накопленные в нём минуты (для «пиков продуктивности»)."""

    hour: int
    focus_minutes: int
    total_minutes: int


@dataclass(frozen=True, slots=True)
class Trend:
    """Сравнение с предыдущим периодом."""

    focus_minutes: int
    previous_focus_minutes: int
    direction: Direction

    @property
    def delta_minutes(self) -> int:
        return self.focus_minutes - self.previous_focus_minutes

    @property
    def delta_percent(self) -> int | None:
        if self.previous_focus_minutes == 0:
            return None
        return round(self.delta_minutes * 100 / self.previous_focus_minutes)


@dataclass(frozen=True, slots=True)
class PeriodReport:
    """Полный отчёт за период: то, что рисуется на картинке и в тексте."""

    period: PeriodKind
    start_local: datetime
    end_local: datetime
    total_minutes: int
    focus_minutes: int
    by_category: tuple[CategoryTotal, ...] = field(default_factory=tuple)
    plan_vs_fact: tuple[PlanVsFactRow, ...] = field(default_factory=tuple)
    peaks: tuple[HourBucket, ...] = field(default_factory=tuple)
    hourly: tuple[HourBucket, ...] = field(default_factory=tuple)
    trend: Trend | None = None
    planned_minutes: int = 0
    events_planned: int = 0
    events_done: int = 0

    @property
    def focus_share(self) -> float:
        if self.total_minutes <= 0:
            return 0.0
        return round(self.focus_minutes / self.total_minutes, 3)

    def category_minutes(self, category: str) -> int:
        """Минуты конкретной категории (0, если её не было)."""
        for row in self.by_category:
            if row.category == category:
                return row.minutes
        return 0

    @property
    def empty(self) -> bool:
        return self.total_minutes == 0 and self.planned_minutes == 0


def period_bounds(period: PeriodKind, now_local: datetime) -> tuple[datetime, datetime]:
    """Границы текущего периода в локальной зоне: день / неделя (пн–вс) / месяц."""
    if period is PeriodKind.DAY:
        return day_bounds_local(now_local.date(), now_local.tzinfo)
    if period is PeriodKind.WEEK:
        monday = now_local.date() - timedelta(days=now_local.weekday())
        start, _ = day_bounds_local(monday, now_local.tzinfo)
        return start, start + timedelta(days=7)
    first = now_local.date().replace(day=1)
    start, _ = day_bounds_local(first, now_local.tzinfo)
    next_month = (first + timedelta(days=32)).replace(day=1)
    end, _ = day_bounds_local(next_month, now_local.tzinfo)
    return start, end


def previous_bounds(period: PeriodKind, start_local: datetime, end_local: datetime):
    """Границы предыдущего периода такой же длительности."""
    length = end_local - start_local
    return start_local - length, start_local


def split_log(log: LogLike, *, tz, now_utc: datetime) -> list[Segment]:
    """Разрезает запись на отрезки по локальным суткам.

    Незакрытая запись (активный таймер) считается до ``now_utc``.
    """
    end_utc = log.end_at or now_utc
    if end_utc <= log.start_at:
        return []
    segments: list[Segment] = []
    cursor = log.start_at
    while cursor < end_utc:
        local = cursor.astimezone(tz)
        next_midnight_local = datetime.combine(
            local.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz
        )
        next_midnight_utc = next_midnight_local.astimezone(UTC)
        segment_end = min(end_utc, next_midnight_utc)
        segments.append(
            Segment(
                category=log.category,
                start_local=cursor.astimezone(tz),
                end_local=segment_end.astimezone(tz),
            )
        )
        cursor = segment_end
    return segments


def clip_segment(
    segment: Segment, window_start: datetime, window_end: datetime
) -> Segment | None:
    """Обрезает отрезок границами окна; None, если пересечения нет."""
    start = max(segment.start_local, window_start)
    end = min(segment.end_local, window_end)
    if end <= start:
        return None
    return Segment(category=segment.category, start_local=start, end_local=end)


def segments_in_window(
    logs: Iterable[LogLike],
    *,
    tz,
    window_start: datetime,
    window_end: datetime,
    now_utc: datetime,
) -> list[Segment]:
    """Все отрезки записей, попавшие в окно (с обрезкой по границам)."""
    result: list[Segment] = []
    for log in logs:
        for segment in split_log(log, tz=tz, now_utc=now_utc):
            clipped = clip_segment(segment, window_start, window_end)
            if clipped is not None:
                result.append(clipped)
    return result


def _minutes(seconds: float) -> int:
    return int(seconds // 60)


def total_minutes(segments: Sequence[Segment]) -> int:
    """Суммарные минуты отрезков (сначала секунды, потом округление — без потерь)."""
    return _minutes(sum(segment.seconds for segment in segments))


def focus_minutes(segments: Sequence[Segment]) -> int:
    """Минуты в фокусных категориях (docs/DECISIONS.md D-03)."""
    return _minutes(sum(s.seconds for s in segments if is_focus_category(s.category)))


def planned_minutes(
    events: Iterable[EventLike],
    *,
    tz,
    window_start: datetime,
    window_end: datetime,
) -> tuple[int, int]:
    """Плановые минуты и количество запланированных событий в окне.

    Отменённые и перенесённые события в план не входят (docs/DECISIONS.md D-10).
    """
    seconds = 0.0
    count = 0
    for event in events:
        status = EventStatus(event.status)
        if not status.counts_as_plan:
            continue
        for start_local, end_local in occurrences_between(
            anchor_start=event.start_at.astimezone(tz),
            duration=event.end_at - event.start_at,
            rule=event.repeat_rule,
            window_start=window_start,
            window_end=window_end,
            exceptions=event.exceptions or (),
        ):
            clipped_start = max(start_local, window_start)
            clipped_end = min(end_local, window_end)
            if clipped_end <= clipped_start:
                continue
            seconds += (clipped_end - clipped_start).total_seconds()
            count += 1
    return _minutes(seconds), count


def planned_by_category(
    events: Iterable[EventLike],
    *,
    tz,
    window_start: datetime,
    window_end: datetime,
) -> dict[str | None, int]:
    """Плановые минуты по категориям."""
    buckets: dict[str | None, float] = {}
    for event in events:
        status = EventStatus(event.status)
        if not status.counts_as_plan:
            continue
        for start_local, end_local in occurrences_between(
            anchor_start=event.start_at.astimezone(tz),
            duration=event.end_at - event.start_at,
            rule=event.repeat_rule,
            window_start=window_start,
            window_end=window_end,
            exceptions=event.exceptions or (),
        ):
            clipped_start = max(start_local, window_start)
            clipped_end = min(end_local, window_end)
            if clipped_end <= clipped_start:
                continue
            buckets[event.category] = buckets.get(event.category, 0.0) + (
                clipped_end - clipped_start
            ).total_seconds()
    return {category: _minutes(seconds) for category, seconds in buckets.items()}


def hourly_buckets(segments: Sequence[Segment]) -> tuple[HourBucket, ...]:
    """24 корзины по часам локального времени: фокус и всё время."""
    focus = [0.0] * 24
    total = [0.0] * 24
    for segment in segments:
        remaining_start = segment.start_local
        while remaining_start < segment.end_local:
            hour_end = remaining_start.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
            chunk_end = min(hour_end, segment.end_local)
            seconds = (chunk_end - remaining_start).total_seconds()
            total[remaining_start.hour] += seconds
            if is_focus_category(segment.category):
                focus[remaining_start.hour] += seconds
            remaining_start = chunk_end
    return tuple(
        HourBucket(hour=hour, focus_minutes=_minutes(focus[hour]), total_minutes=_minutes(total[hour]))
        for hour in range(24)
    )


def top_peaks(buckets: Sequence[HourBucket], *, limit: int = 3) -> tuple[HourBucket, ...]:
    """Часы с наибольшим фокусом (пики продуктивности)."""
    productive = [bucket for bucket in buckets if bucket.focus_minutes > 0]
    productive.sort(key=lambda bucket: (-bucket.focus_minutes, bucket.hour))
    return tuple(productive[:limit])


def category_totals(segments: Sequence[Segment]) -> tuple[CategoryTotal, ...]:
    """Разрез по категориям: минуты, доля, признак «фокус»."""
    buckets: dict[str, float] = {}
    for segment in segments:
        buckets[segment.category] = buckets.get(segment.category, 0.0) + segment.seconds
    grand_total = sum(buckets.values())
    order = {category.value: index for index, category in enumerate(CATEGORY_ORDER)}
    rows = [
        CategoryTotal(
            category=category,
            minutes=_minutes(seconds),
            share=round(seconds / grand_total, 3) if grand_total else 0.0,
            is_focus=is_focus_category(category),
        )
        for category, seconds in buckets.items()
    ]
    rows.sort(key=lambda row: (-row.minutes, order.get(row.category or "", 99)))
    return tuple(rows)


def build_trend(
    current_focus: int, previous_focus: int, *, previous_known: bool
) -> Trend | None:
    """Тренд по фокусу: сравнение с прошлым периодом."""
    if not previous_known:
        return None
    if previous_focus == 0 and current_focus == 0:
        direction = Direction.FLAT
    elif previous_focus == 0:
        direction = Direction.UP
    else:
        delta = current_focus - previous_focus
        threshold = max(5, int(previous_focus * 0.05))
        if abs(delta) < threshold:
            direction = Direction.FLAT
        else:
            direction = Direction.UP if delta > 0 else Direction.DOWN
    return Trend(
        focus_minutes=current_focus,
        previous_focus_minutes=previous_focus,
        direction=direction,
    )


def build_report(
    *,
    period: PeriodKind,
    now_local: datetime,
    logs: Sequence[LogLike],
    events: Sequence[EventLike] = (),
    now_utc: datetime | None = None,
    previous_logs: Sequence[LogLike] | None = None,
    previous_events: Sequence[EventLike] | None = None,
) -> PeriodReport:
    """Собирает отчёт за период.

    ``previous_logs`` включает сравнение с прошлым периодом; без него тренда нет.
    """
    tz = now_local.tzinfo
    moment_utc = now_utc or now_local.astimezone(UTC)
    start_local, end_local = period_bounds(period, now_local)
    segments = segments_in_window(
        logs, tz=tz, window_start=start_local, window_end=end_local, now_utc=moment_utc
    )
    planned, events_planned = planned_minutes(
        events, tz=tz, window_start=start_local, window_end=end_local
    )
    actual_by_category = category_totals(segments)
    planned_categories = planned_by_category(
        events, tz=tz, window_start=start_local, window_end=end_local
    )
    plan_rows: list[PlanVsFactRow] = []
    for category in sorted(
        set(planned_categories) | {row.category for row in actual_by_category},
        key=lambda item: item or "",
    ):
        plan_rows.append(
            PlanVsFactRow(
                category=category,
                planned_minutes=planned_categories.get(category, 0),
                actual_minutes=next(
                    (row.minutes for row in actual_by_category if row.category == category), 0
                ),
            )
        )
    buckets = hourly_buckets(segments)

    trend: Trend | None = None
    if previous_logs is not None:
        prev_start, prev_end = (
            previous_bounds(period, start_local, end_local)
            if period is not PeriodKind.MONTH
            else _previous_month_bounds(start_local)
        )
        prev_segments = segments_in_window(
            previous_logs,
            tz=tz,
            window_start=prev_start,
            window_end=prev_end,
            now_utc=moment_utc,
        )
        trend = build_trend(
            focus_minutes(segments), focus_minutes(prev_segments), previous_known=True
        )

    done_ids = {
        event.id for event in events if EventStatus(event.status) is EventStatus.DONE
    }

    return PeriodReport(
        period=period,
        start_local=start_local,
        end_local=end_local,
        total_minutes=total_minutes(segments),
        focus_minutes=focus_minutes(segments),
        by_category=actual_by_category,
        plan_vs_fact=tuple(plan_rows),
        peaks=top_peaks(buckets),
        hourly=buckets,
        trend=trend,
        planned_minutes=planned,
        events_planned=events_planned,
        events_done=len(done_ids),
    )


def _previous_month_bounds(start_local: datetime) -> tuple[datetime, datetime]:
    """Границы предыдущего календарного месяца."""
    first = start_local.date().replace(day=1)
    prev_last = first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    start, _ = day_bounds_local(prev_first, start_local.tzinfo)
    end, _ = day_bounds_local(first, start_local.tzinfo)
    return start, end


def top_category(report: PeriodReport) -> CategoryTotal | None:
    """Самая «дорогая» категория периода (без осуждения — просто факт)."""
    return report.by_category[0] if report.by_category else None


__all__ = [
    "CategoryTotal",
    "Direction",
    "HourBucket",
    "LogLike",
    "EventLike",
    "PeriodKind",
    "PeriodReport",
    "PlanVsFactRow",
    "Segment",
    "Trend",
    "build_report",
    "build_trend",
    "category_totals",
    "clip_segment",
    "focus_minutes",
    "hourly_buckets",
    "period_bounds",
    "planned_by_category",
    "planned_minutes",
    "previous_bounds",
    "segments_in_window",
    "split_log",
    "top_category",
    "top_peaks",
    "total_minutes",
]
