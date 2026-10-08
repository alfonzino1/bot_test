"""Сборка данных главного меню и экрана «Сегодня»."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import EventStatus
from chronos.i18n import t
from chronos.models import User
from chronos.repositories import time_logs as time_logs_repo
from chronos.services import analytics, schedule
from chronos.services.schedule import Occurrence
from chronos.utils.formatting import format_duration, format_events_count, format_time
from chronos.utils.timezones import day_bounds_local, to_utc


@dataclass(frozen=True, slots=True)
class TodaySummary:
    """Короткая сводка дня для главного меню: события, фокус, ближайшее."""

    events_count: int
    focus_minutes: int
    next_occurrence: Occurrence | None


async def today_summary(
    session: AsyncSession, user: User, *, now_utc: datetime
) -> TodaySummary:
    """Считает сводку текущего локального дня (кнопка 🏠 Меню и /menu)."""
    tz = schedule.user_zone(user)
    now_local = now_utc.astimezone(tz)
    start_local, end_local = day_bounds_local(now_local.date(), tz)
    occurrences = await schedule.occurrences_for_window(
        session, user, window_start_local=start_local, window_end_local=end_local
    )
    logs = await time_logs_repo.list_for_window(
        session, user.id, to_utc(start_local), to_utc(end_local)
    )
    report = analytics.build_report(
        period=analytics.PeriodKind.DAY,
        now_local=now_local,
        logs=logs,
        now_utc=now_utc,
    )
    planned = [item for item in occurrences if item.status.counts_as_plan]
    upcoming = next(
        (
            item
            for item in planned
            if item.start_local >= now_local
            and item.status not in (EventStatus.CANCELED, EventStatus.MOVED)
        ),
        None,
    )
    return TodaySummary(
        events_count=len(planned),
        focus_minutes=report.focus_minutes,
        next_occurrence=upcoming,
    )


def build_menu_text(user: User, summary: TodaySummary) -> str:
    """Текст главного меню по макету ТЗ."""
    lines: list[str] = []
    if user.name:
        lines.append(t("menu.title", name=user.name))
    else:
        lines.append(t("menu.title_anon"))
    lines.append(
        t(
            "menu.summary",
            events=format_events_count(summary.events_count),
            focus=format_duration(summary.focus_minutes),
        )
    )
    if summary.next_occurrence is not None:
        lines.append(
            t(
                "menu.next_event",
                time=format_time(summary.next_occurrence.start_local),
                title=summary.next_occurrence.title,
            )
        )
    elif summary.events_count == 0:
        lines.append(t("menu.no_events"))
    lines.append("")
    lines.append(t("menu.hint"))
    return "\n".join(lines)


__all__ = ["TodaySummary", "build_menu_text", "today_summary"]
