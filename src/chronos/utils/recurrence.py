"""Повторяемость событий: разбор правил и вычисление вхождений.

Правило хранится строкой в подмножестве RFC 5545 (см. docs/DECISIONS.md D-07):
``none`` | ``daily`` | ``weekdays`` | ``weekly:MO,WE,FR``.

Все вычисления идут по локальному настенному времени пользователя, а на выходе
получаются aware-datetime в его зоне.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from chronos.constants import (
    REPEAT_WEEKLY_PREFIX,
    WEEKDAY_CODES,
    WEEKDAY_RU,
    RepeatRule,
)
from chronos.i18n import t
from chronos.logging_setup import logger

#: Предохранитель: максимум дней, которые просматривает перебор вхождений.
MAX_ITERATION_DAYS = 4000
#: Окно поиска «следующих вхождений», если явно не задано.
DEFAULT_SEARCH_DAYS = 366

_NONE_VALUE = RepeatRule.NONE.value


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """Разобранное правило повтора."""

    kind: RepeatRule
    weekdays: frozenset[int] = field(default_factory=frozenset)  # 0 = понедельник

    @property
    def is_recurring(self) -> bool:
        return self.kind is not RepeatRule.NONE


def parse_rule(rule: str | None) -> RuleSpec:
    """Разбирает строку правила. Неизвестное правило трактуется как разовое событие."""
    if not rule:
        return RuleSpec(RepeatRule.NONE)
    raw = rule.strip().lower()
    if raw == _NONE_VALUE:
        return RuleSpec(RepeatRule.NONE)
    if raw == RepeatRule.DAILY.value:
        return RuleSpec(RepeatRule.DAILY)
    if raw == RepeatRule.WEEKDAYS.value:
        return RuleSpec(RepeatRule.WEEKDAYS)
    if raw.startswith(REPEAT_WEEKLY_PREFIX):
        codes = [code.strip().upper() for code in raw[len(REPEAT_WEEKLY_PREFIX) :].split(",")]
        days = {WEEKDAY_CODES.index(code) for code in codes if code in WEEKDAY_CODES}
        if days:
            return RuleSpec(RepeatRule.WEEKLY, frozenset(days))
        return RuleSpec(RepeatRule.WEEKLY, frozenset({0}))
    logger.warning("Неизвестное правило повтора: {!r} — считаю разовым", rule)
    return RuleSpec(RepeatRule.NONE)


def build_rule(kind: RepeatRule, weekdays: Collection[int] | None = None) -> str:
    """Собирает строку правила из вида повтора и набора дней недели."""
    if kind is RepeatRule.WEEKLY:
        days = sorted(weekdays) if weekdays else [0]
        codes = ",".join(WEEKDAY_CODES[day] for day in days)
        return f"{REPEAT_WEEKLY_PREFIX}{codes}"
    return kind.value


def describe_rule(rule: str) -> str:
    """«каждый день», «по будням», «по пн, ср» — для интерфейса."""
    spec = parse_rule(rule)
    if spec.kind is RepeatRule.DAILY:
        return t("format.repeat.daily")
    if spec.kind is RepeatRule.WEEKDAYS:
        return t("format.repeat.weekdays")
    if spec.kind is RepeatRule.WEEKLY:
        days = ", ".join(WEEKDAY_RU[WEEKDAY_CODES[day]] for day in sorted(spec.weekdays))
        return t("format.repeat.weekly", days=days)
    return ""


def matches_date(spec: RuleSpec, target) -> bool:  # type: ignore[no-untyped-def]
    """Попадает ли конкретная дата в правило повтора."""
    if spec.kind is RepeatRule.DAILY:
        return True
    if spec.kind is RepeatRule.WEEKDAYS:
        return target.weekday() < 5
    if spec.kind is RepeatRule.WEEKLY:
        return target.weekday() in spec.weekdays
    return False


def _wall(moment: datetime) -> datetime:
    """Настенное (naive) время момента: арифметика по календарю пользователя."""
    return moment.replace(tzinfo=None)


def _attach(naive: datetime, reference: datetime) -> datetime:
    """Возвращает исходную зону к настенному времени."""
    return naive.replace(tzinfo=reference.tzinfo)


def iter_occurrences(
    *,
    anchor_start: datetime,
    duration: timedelta,
    rule: str | None,
    window_start: datetime,
    window_end: datetime,
    exceptions: Collection[str] = (),
) -> Iterator[tuple[datetime, datetime]]:
    """Вхождения серии, попавшие в окно ``[window_start, window_end]``.

    Все datetime — aware в одной локальной зоне. ``exceptions`` — ISO-даты
    вхождений, которые нужно пропустить (перенос конкретного вхождения).
    """
    spec = parse_rule(rule)
    tzinfo = window_start.tzinfo
    anchor_naive = _wall(anchor_start)
    window_from = max(_wall(window_start), anchor_naive)
    window_to = _wall(window_end)
    if window_to < window_from:
        return
    skip = set(exceptions)

    candidates: list[datetime] = []
    if not spec.is_recurring:
        if window_from <= anchor_naive <= window_to:
            candidates.append(anchor_naive)
    else:
        day = window_from.date()
        last_day = window_to.date()
        scanned = 0
        while day <= last_day:
            scanned += 1
            if scanned > MAX_ITERATION_DAYS:  # pragma: no cover - защитный предел
                logger.warning(
                    "Перебор вхождений прерван на {} днях (rule={!r})", scanned, rule
                )
                break
            if matches_date(spec, day):
                occurrence = datetime.combine(day, anchor_naive.time())
                if window_from <= occurrence <= window_to:
                    candidates.append(occurrence)
            day += timedelta(days=1)

    for occurrence in candidates:
        if occurrence.date().isoformat() in skip:
            continue
        yield (
            occurrence.replace(tzinfo=tzinfo) if tzinfo else occurrence,
            (occurrence + duration).replace(tzinfo=tzinfo) if tzinfo else occurrence + duration,
        )


def occurrences_between(
    *,
    anchor_start: datetime,
    duration: timedelta,
    rule: str | None,
    window_start: datetime,
    window_end: datetime,
    exceptions: Collection[str] = (),
) -> list[tuple[datetime, datetime]]:
    """Список вхождений в окне (см. ``iter_occurrences``)."""
    return list(
        iter_occurrences(
            anchor_start=anchor_start,
            duration=duration,
            rule=rule,
            window_start=window_start,
            window_end=window_end,
            exceptions=exceptions,
        )
    )


def next_occurrences(
    *,
    anchor_start: datetime,
    duration: timedelta,
    rule: str | None,
    after: datetime,
    count: int,
    exceptions: Collection[str] = (),
    search_days: int = DEFAULT_SEARCH_DAYS,
) -> list[tuple[datetime, datetime]]:
    """Первые ``count`` вхождений, начинающиеся не раньше ``after``."""
    found: list[tuple[datetime, datetime]] = []
    window_end = after + timedelta(days=search_days)
    for occurrence in iter_occurrences(
        anchor_start=anchor_start,
        duration=duration,
        rule=rule,
        window_start=after,
        window_end=window_end,
        exceptions=exceptions,
    ):
        found.append(occurrence)
        if len(found) >= count:
            break
    return found


def first_occurrence_after(
    *,
    anchor_start: datetime,
    duration: timedelta,
    rule: str | None,
    after: datetime,
    exceptions: Collection[str] = (),
) -> tuple[datetime, datetime] | None:
    """Ближайшее вхождение после момента ``after`` (или None, если серия кончилась)."""
    found = next_occurrences(
        anchor_start=anchor_start,
        duration=duration,
        rule=rule,
        after=after,
        count=1,
        exceptions=exceptions,
    )
    return found[0] if found else None


__all__ = [
    "RuleSpec",
    "build_rule",
    "describe_rule",
    "first_occurrence_after",
    "iter_occurrences",
    "matches_date",
    "next_occurrences",
    "occurrences_between",
    "parse_rule",
]
