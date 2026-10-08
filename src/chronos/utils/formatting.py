"""Форматирование значений для интерфейса (все тексты берутся из i18n).

Здесь нет бизнес-логики: только превращение чисел/дат в человекочитаемые строки.
"""

from __future__ import annotations

from datetime import date, datetime, time

from chronos.constants import MONTH_RU_GENITIVE, WEEKDAY_CODES, WEEKDAY_RU, RepeatRule
from chronos.i18n import t


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    """Выбор формы существительного по русским правилам (1 событие / 2 события)."""
    count = abs(int(number))
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def format_events_count(count: int) -> str:
    """«3 события», «1 событие», «5 событий»."""
    return f"{count} {plural_ru(count, t('plural.event.one'), t('plural.event.few'), t('plural.event.many'))}"


def format_duration(minutes: int) -> str:
    """«1ч 12мин», «45мин», «2ч» — единый короткий формат длительности."""
    total = max(0, int(minutes))
    hours, rest = divmod(total, 60)
    if hours and rest:
        return t("format.duration.hours_minutes", hours=hours, minutes=rest)
    if hours:
        return t("format.duration.hours", hours=hours)
    return t("format.duration.minutes", minutes=rest)


def format_time(value: datetime | time) -> str:
    """«15:00» из datetime или time."""
    return f"{value.hour:02d}:{value.minute:02d}"


def format_time_range(start: datetime | time, end: datetime | time) -> str:
    """«15:00–16:30» (тире-эн-даш, как в макетах)."""
    return f"{format_time(start)}–{format_time(end)}"


def format_date_short(value: date) -> str:
    """«12.05» — компактная дата для кнопок и списков."""
    return f"{value.day:02d}.{value.month:02d}"


def format_date_full(value: date) -> str:
    """«12 мая» — дата без года для заголовков."""
    return f"{value.day} {MONTH_RU_GENITIVE[value.month - 1]}"


def format_weekday(value: date) -> str:
    """«вт» — короткий день недели."""
    return WEEKDAY_RU[WEEKDAY_CODES[value.weekday()]]


def humanize_date(target: date, today: date) -> str:
    """«сегодня» / «завтра» / «послезавтра» / «12 мая»."""
    delta = (target - today).days
    if delta == 0:
        return t("format.date.today")
    if delta == 1:
        return t("format.date.tomorrow")
    if delta == 2:
        return t("format.date.day_after_tomorrow")
    if delta == -1:
        return t("format.date.yesterday")
    return format_date_full(target)


def humanize_datetime(moment: datetime, now: datetime) -> str:
    """«завтра 15:00»."""
    return f"{humanize_date(moment.date(), now.date())} {format_time(moment)}"


def format_when(start: datetime, end: datetime, now: datetime) -> str:
    """«завтра 15:00–16:00» — для превью и подтверждений."""
    return f"{humanize_date(start.date(), now.date())} {format_time_range(start, end)}"


def format_repeat(rule: str) -> str:
    """«🔁 каждый день», «🔁 по будням», «🔁 по пн, ср»."""
    from chronos.utils.recurrence import describe_rule  # локальный импорт: без циклов

    if rule == RepeatRule.NONE.value:
        return ""
    return f"🔁 {describe_rule(rule)}"


def format_reminder(offset_min: int | None) -> str:
    """Подпись выбранного напоминания для превью."""
    if offset_min is None:
        return t("add.reminder_off")
    if offset_min <= 0:
        return t("add.reminder_immediate")
    if offset_min < 60:
        return t("add.reminder_minutes", minutes=offset_min)
    return t("add.reminder_hours", hours=offset_min // 60)


__all__ = [
    "format_date_full",
    "format_date_short",
    "format_duration",
    "format_events_count",
    "format_reminder",
    "format_repeat",
    "format_time",
    "format_time_range",
    "format_when",
    "format_weekday",
    "humanize_date",
    "humanize_datetime",
    "plural_ru",
]
