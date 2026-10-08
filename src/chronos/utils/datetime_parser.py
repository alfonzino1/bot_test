"""Разбор естественного текста: даты, время, интервалы, длительности.

Пример: ``«Встреча завтра 15:00-16:00 #работа»`` → черновик события с датой,
временем, категорией и напоминанием.

Модуль намеренно не знает о Telegram и БД: на вход приходит ``now_local``
(aware в зоне пользователя), на выход — dataclass-черновик. Это делает парсер
полностью покрываемым юнит-тестами.

Что понимает:

* даты: ``сегодня``, ``завтра``, ``послезавтра``, ``через 3 дня``,
  ``12.05``, ``12.05.2026``, ``2026-05-12``, ``в пн``, ``в понедельник``;
* время: ``15:00``, ``15.00``, ``9:30``, диапазон ``15:00-16:30``,
  ``утром`` / ``днём`` / ``вечером`` / ``ночью``;
* повтор: ``каждый день``, ``по будням``, ``каждую неделю``;
* категорию: ``#работа``, ``#учёба``, ``#спорт``, любая своя метка;
* напоминание: ``за 15 мин``, ``за час``, ``в момент``, ``без напоминания``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from chronos.constants import (
    CATEGORY_ALIASES,
    DEFAULT_EVENT_MINUTES,
    DEFAULT_REMINDER_OFFSET_MIN,
    REMINDER_IMMEDIATE,
    REMINDER_OFF,
    RepeatRule,
)
from chronos.utils.recurrence import build_rule

# ── Регулярные выражения ──────────────────────────────────────────────────────

_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DAY_MONTH_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?(?!\d)")
_TIME_RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[:.](\d{2})\s*(?:-|–|—|до)\s*(\d{1,2})[:.](\d{2})(?!\d)"
)
_TIME_RE = re.compile(r"(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)")
_REL_DAYS_RE = re.compile(r"через\s+(\d{1,3})\s*(?:день|дня|дней)\b", re.IGNORECASE)
_REL_HOURS_RE = re.compile(r"через\s+(\d{1,3})\s*(?:час|часа|часов)\b", re.IGNORECASE)
_REL_MINUTES_RE = re.compile(r"через\s+(\d{1,3})\s*(?:минуту|минуты|минут)\b", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#([\w\-]+)", re.UNICODE)
_INTERVAL_RE = re.compile(
    r"(?:с\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|–|—|до)\s*"
    r"(\d{1,2})(?:[:.](\d{2}))?(?!\d)",
    re.IGNORECASE,
)
_MUTE_DURATION_RE = re.compile(
    r"^\s*(\d{1,3})\s*(?:h|ч|час(?:а|ов)?|m|м|мин(?:ут[уы]?)?)\s*$", re.IGNORECASE
)
_REMINDER_MINUTES_RE = re.compile(
    r"за\s*(\d{1,3})\s*(?:мин(?:ут[уы]?)?|м)\b", re.IGNORECASE
)
_REMINDER_HOURS_RE = re.compile(r"за\s*(\d{1,2})\s*(?:ч|час(?:а|ов)?)\b", re.IGNORECASE)

#: Слова-даты.
_TODAY_WORDS = ("сегодня", "today")
_TOMORROW_WORDS = ("завтра", "tomorrow")
_DAY_AFTER_WORDS = ("послезавтра",)
_YESTERDAY_WORDS = ("вчера", "yesterday")

#: Дни недели: алиасы → индекс (0 = понедельник).
_WEEKDAY_ALIASES: dict[str, int] = {
    "пн": 0, "пон": 0, "понедельник": 0, "monday": 0, "mon": 0,
    "вт": 1, "вторник": 1, "tuesday": 1, "tue": 1,
    "ср": 2, "среда": 2, "среду": 2, "wednesday": 2, "wed": 2,
    "чт": 3, "четверг": 3, "thursday": 3, "thu": 3,
    "пт": 4, "пятница": 4, "пятницу": 4, "friday": 4, "fri": 4,
    "сб": 5, "суббота": 5, "субботу": 5, "saturday": 5, "sat": 5,
    "вс": 6, "воскресенье": 6, "sunday": 6, "sun": 6,
}

#: Слова-части суток → час по умолчанию.
_DAY_PART_HOURS: dict[str, int] = {
    "утром": 9, "утра": 9,
    "днём": 14, "днем": 14, "обед": 13,
    "вечером": 19, "вечера": 19,
    "ночью": 22,
}

#: Маркеры «напоминать не надо».
_NO_REMINDER_WORDS = (
    "без напоминания",
    "не напоминай",
    "не надо напоминать",
    "без напоминаний",
)
#: Маркеры «напомнить в момент события».
_NOW_REMINDER_WORDS = ("в момент", "ровно в", "вовремя", "в начале")

#: Словесные напоминания без цифр: (фраза, смещение в минутах).
_WORD_REMINDERS: tuple[tuple[str, int], ...] = (
    ("за полчаса", 30),
    ("за час", 60),
)

#: Маркеры повтора.
_DAILY_WORDS = ("каждый день", "ежедневно", "каждодневно")
_WEEKDAYS_WORDS = ("по будням", "по будням", "в будни", "по рабочим дням")
_WEEKLY_WORDS = ("каждую неделю", "еженедельно", "каждый понедельник")


@dataclass(frozen=True, slots=True)
class DraftEvent:
    """Черновик события, собранный из текста пользователя."""

    title: str = ""
    #: Выбранная локальная дата, даже если время ещё не названо.
    date_local: date | None = None
    start_local: datetime | None = None
    end_local: datetime | None = None
    repeat_rule: str = RepeatRule.NONE.value
    category: str | None = None
    category_custom_label: str | None = None
    reminder_offset: int | None = DEFAULT_REMINDER_OFFSET_MIN
    reminder_specified: bool = False
    #: Была ли в тексте явная дата (если нет — время в прошлом переносим на завтра).
    date_specified: bool = False
    #: Чего не хватает для создания события: ``title``, ``time``.
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        return not self.missing and bool(self.title)

    @property
    def duration_minutes(self) -> int:
        if self.start_local and self.end_local:
            return int((self.end_local - self.start_local).total_seconds() // 60)
        return DEFAULT_EVENT_MINUTES


#: Предлоги, которые остаются висеть после вырезания даты/времени.
_DANGLING_PREPOSITIONS = frozenset(
    {"в", "во", "на", "с", "со", "к", "ко", "до", "по", "за", "у", "о", "об", "от", "для"}
)


def _clean(text: str) -> str:
    """Нормализует пробелы, срезает висящую пунктуацию и предлоги по краям."""
    cleaned = re.sub(r"\s+", " ", text).strip(" ,;·—-")
    words = cleaned.split()
    while words and words[0].lower().strip(" ,.") in _DANGLING_PREPOSITIONS:
        words.pop(0)
    while words and words[-1].lower().strip(" ,.") in _DANGLING_PREPOSITIONS:
        words.pop()
    return " ".join(words).strip(" ,;·—-")


def _attach(naive: datetime, now_local: datetime) -> datetime:
    return naive.replace(tzinfo=now_local.tzinfo)


def _next_weekday(now_local: datetime, weekday: int) -> date:
    """Ближайший день недели, начиная с сегодняшнего (сегодня тоже подходит)."""
    today = now_local.date()
    delta = (weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def parse_interval_text(text: str | None) -> tuple[time, time] | None:
    """Разбирает интервал времени: ``9:30-18:00``, ``с 9 до 18``, ``9-18``.

    Используется онбордингом и настройками (рабочие часы, тихий час).
    Поддерживает интервалы через полночь: ``23:00-8:00``.
    """
    if not text:
        return None
    match = _INTERVAL_RE.search(text)
    if not match:
        return None
    start_hour, start_minute, end_hour, end_minute = match.groups()
    try:
        start = time(int(start_hour) % 24, int(start_minute or 0))
        end = time(int(end_hour) % 24, int(end_minute or 0))
    except ValueError:
        return None
    return start, end


def parse_duration_text(text: str | None) -> timedelta | None:
    """Разбирает длительность для ``/mute``: ``2h``, ``2ч``, ``30m``, ``45 минут``."""
    if not text:
        return None
    raw = text.strip().lower()
    match = _MUTE_DURATION_RE.match(raw)
    if not match:
        # «2 часа 30 минут» / «1h30m»
        parts = re.findall(r"(\d{1,3})\s*(h|ч|m|м)", raw)
        if not parts:
            return None
        total = timedelta()
        for amount, unit in parts:
            total += (
                timedelta(minutes=int(amount))
                if unit in ("m", "м")
                else timedelta(hours=int(amount))
            )
        return total or None
    amount = int(match.group(1))
    unit = match.group(0).strip()[-1].lower()
    if unit in ("h", "ч") or "час" in raw:
        return timedelta(hours=amount)
    return timedelta(minutes=amount)


def parse_date_text(text: str | None, *, now_local: datetime) -> date | None:
    """Разбирает только дату (для шага «Другая дата» в мастере).

    ``None`` означает «не понял» — вызывающий код покажет подсказку.
    """
    if not text:
        return None
    raw = text.strip().lower()
    if any(word in raw for word in _TODAY_WORDS):
        return now_local.date()
    if any(word in raw for word in _TOMORROW_WORDS):
        return now_local.date() + timedelta(days=1)
    if any(word in raw for word in _DAY_AFTER_WORDS):
        return now_local.date() + timedelta(days=2)
    if any(word in raw for word in _YESTERDAY_WORDS):
        return now_local.date() - timedelta(days=1)

    relative = _REL_DAYS_RE.search(raw)
    if relative:
        return now_local.date() + timedelta(days=int(relative.group(1)))

    iso = _ISO_DATE_RE.search(raw)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    day_month = _DAY_MONTH_RE.search(raw)
    if day_month:
        day, month, year = day_month.groups()
        try:
            return date(int(year) if year else now_local.year, int(month), int(day))
        except ValueError:
            return None

    weekday = _match_weekday(raw)
    if weekday is not None:
        return _next_weekday(now_local, weekday)
    return None


def parse_time_text(text: str | None, *, on_date: date, now_local: datetime) -> datetime | None:
    """Разбирает «15:00» / «в 15:00» / «вечером» в конкретный момент.

    Если время уже прошло на указанную дату — возвращает момент как есть,
    решение «переносить на завтра» принимает вызывающий код.
    """
    if not text:
        return None
    raw = text.strip().lower()
    match = _TIME_RE.search(raw)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return _attach(datetime.combine(on_date, time(hour, minute)), now_local)
    for word, hour in _DAY_PART_HOURS.items():
        if word in raw:
            return _attach(datetime.combine(on_date, time(hour, 0)), now_local)
    return None


def parse_time_range_text(
    text: str | None, *, on_date: date, now_local: datetime, default_minutes: int = DEFAULT_EVENT_MINUTES
) -> tuple[datetime, datetime] | None:
    """Разбирает ``15:00-16:30`` или одиночное время (тогда конец — по умолчанию)."""
    if not text:
        return None
    raw = text.strip()
    match = _TIME_RANGE_RE.search(raw)
    if match:
        start_hour, start_minute, end_hour, end_minute = (int(g) for g in match.groups())
        if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
            return None
        start = _attach(datetime.combine(on_date, time(start_hour, start_minute)), now_local)
        end = _attach(datetime.combine(on_date, time(end_hour, end_minute)), now_local)
        if end <= start:  # интервал через полночь
            end += timedelta(days=1)
        return start, end
    single = parse_time_text(raw, on_date=on_date, now_local=now_local)
    if single is None:
        return None
    return single, single + timedelta(minutes=default_minutes)


def _match_weekday(raw: str) -> int | None:
    """Ищет день недели как отдельное слово (``в пн``, ``понедельник``)."""
    for token in re.findall(r"[a-zа-яё]+", raw):
        if token in _WEEKDAY_ALIASES:
            return _WEEKDAY_ALIASES[token]
    return None


def _extract_category(text: str) -> tuple[str | None, str | None, str]:
    """Вынимает ``#метку``. Возвращает (ключ, своя подпись, текст без метки)."""
    match = _HASHTAG_RE.search(text)
    if not match:
        return None, None, text
    tag = match.group(1).strip()
    key = CATEGORY_ALIASES.get(tag.lower())
    if key is not None:
        return key, None, _HASHTAG_RE.sub(" ", text, count=1)
    # Свободная метка пользователя: сохраняем как ключ-строку (Category.CUSTOM).
    return tag, tag, _HASHTAG_RE.sub(" ", text, count=1)


def _extract_reminder(text: str) -> tuple[int | None, bool, str]:
    """Вынимает указание напоминания. Возвращает (смещение, указано_ли, текст)."""
    lowered = text.lower()
    for word in _NO_REMINDER_WORDS:
        if word in lowered:
            return REMINDER_OFF, True, re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    for word in _NOW_REMINDER_WORDS:
        if word in lowered:
            return REMINDER_IMMEDIATE, True, re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    hours = _REMINDER_HOURS_RE.search(text)
    if hours:
        return (
            int(hours.group(1)) * 60,
            True,
            text[: hours.start()] + " " + text[hours.end() :],
        )
    minutes = _REMINDER_MINUTES_RE.search(text)
    if minutes:
        return int(minutes.group(1)), True, text[: minutes.start()] + " " + text[minutes.end() :]
    # Словесные формы без цифр: «за час», «за полчаса».
    for word, offset in _WORD_REMINDERS:
        if word in lowered:
            return offset, True, re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    return DEFAULT_REMINDER_OFFSET_MIN, False, text


def parse_event_text(
    text: str | None,
    *,
    now_local: datetime,
    default_duration_minutes: int = DEFAULT_EVENT_MINUTES,
) -> DraftEvent:
    """Разбирает строку быстрого добавления в черновик события.

    Порядок разбора важен: сначала относительные смещения и метки, затем
    повтор, дата, время. Остаток строки становится названием.
    """
    if not text or not text.strip():
        return DraftEvent(missing=("title", "time"))

    working = text
    repeat_rule = RepeatRule.NONE.value
    repeat_weekday: int | None = None
    missing: list[str] = []

    # 1. Повтор.
    lowered = working.lower()
    for word in _WEEKDAYS_WORDS:
        if word in lowered:
            repeat_rule = RepeatRule.WEEKDAYS.value
            working = re.sub(re.escape(word), " ", working, flags=re.IGNORECASE)
            lowered = working.lower()
            break
    else:
        for word in _DAILY_WORDS:
            if word in lowered:
                repeat_rule = RepeatRule.DAILY.value
                working = re.sub(re.escape(word), " ", working, flags=re.IGNORECASE)
                lowered = working.lower()
                break
        else:
            for word in _WEEKLY_WORDS:
                if word in lowered:
                    repeat_rule = RepeatRule.WEEKLY.value
                    repeat_weekday = working.lower().find("понедельник")
                    repeat_weekday = 0 if repeat_weekday >= 0 else None
                    working = re.sub(re.escape(word), " ", working, flags=re.IGNORECASE)
                    lowered = working.lower()
                    break

    # 2. Относительные смещения «через N дней/часов/минут».
    date_local: date | None = None
    date_specified = False
    time_hint: time | None = None
    relative_days = _REL_DAYS_RE.search(working)
    if relative_days:
        date_local = now_local.date() + timedelta(days=int(relative_days.group(1)))
        date_specified = True
        working = working[: relative_days.start()] + " " + working[relative_days.end() :]
    relative_hours = _REL_HOURS_RE.search(working)
    if relative_hours:
        moment = now_local + timedelta(hours=int(relative_hours.group(1)))
        date_local = moment.date()
        date_specified = True
        time_hint = time(moment.hour, moment.minute)
        working = working[: relative_hours.start()] + " " + working[relative_hours.end() :]
    relative_minutes = _REL_MINUTES_RE.search(working)
    if relative_minutes:
        moment = now_local + timedelta(minutes=int(relative_minutes.group(1)))
        date_local = moment.date()
        date_specified = True
        time_hint = time(moment.hour, moment.minute)
        working = working[: relative_minutes.start()] + " " + working[relative_minutes.end() :]

    # 3. Категория и напоминание.
    category, custom_label, working = _extract_category(working)
    reminder_offset, reminder_specified, working = _extract_reminder(working)

    # 4. Дата.
    if date_local is None:
        word_lowered = working.lower()
        if any(word in word_lowered for word in _DAY_AFTER_WORDS):
            date_local = now_local.date() + timedelta(days=2)
            date_specified = True
            working = _drop_words(working, _DAY_AFTER_WORDS)
        elif any(word in word_lowered for word in _TOMORROW_WORDS):
            date_local = now_local.date() + timedelta(days=1)
            date_specified = True
            working = _drop_words(working, _TOMORROW_WORDS)
        elif any(word in word_lowered for word in _TODAY_WORDS):
            date_local = now_local.date()
            date_specified = True
            working = _drop_words(working, _TODAY_WORDS)
        elif any(word in word_lowered for word in _YESTERDAY_WORDS):
            date_local = now_local.date() - timedelta(days=1)
            date_specified = True
            working = _drop_words(working, _YESTERDAY_WORDS)
        else:
            iso = _ISO_DATE_RE.search(working)
            day_month = _DAY_MONTH_RE.search(working)
            if iso:
                try:
                    date_local = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
                    date_specified = True
                    working = working[: iso.start()] + " " + working[iso.end() :]
                except ValueError:
                    date_local = None
            elif day_month:
                day, month, year = day_month.groups()
                try:
                    date_local = date(
                        int(year) if year else now_local.year, int(month), int(day)
                    )
                    date_specified = True
                    working = working[: day_month.start()] + " " + working[day_month.end() :]
                except ValueError:
                    date_local = None  # «15.30» — это время, не дата
            if date_local is None:
                weekday = _match_weekday(working)
                if weekday is not None:
                    date_local = _next_weekday(now_local, weekday)
                    date_specified = True
                    if repeat_rule == RepeatRule.WEEKLY.value:
                        repeat_weekday = weekday
                    working = _drop_weekday(working)

    # 5. Время.
    start_local: datetime | None = None
    end_local: datetime | None = None
    if time_hint is not None:
        base_date = date_local or now_local.date()
        start_local = _attach(datetime.combine(base_date, time_hint), now_local)
        end_local = start_local + timedelta(minutes=default_duration_minutes)
        date_local = base_date
    else:
        range_match = _TIME_RANGE_RE.search(working)
        single_match = _TIME_RE.search(working)
        if range_match:
            start_hour, start_minute, end_hour, end_minute = (
                int(g) for g in range_match.groups()
            )
            if start_hour <= 23 and end_hour <= 23 and start_minute <= 59 and end_minute <= 59:
                base_date = date_local or now_local.date()
                start_local = _attach(
                    datetime.combine(base_date, time(start_hour, start_minute)), now_local
                )
                end_local = _attach(
                    datetime.combine(base_date, time(end_hour, end_minute)), now_local
                )
                if end_local <= start_local:
                    end_local += timedelta(days=1)
                date_local = base_date
                working = working[: range_match.start()] + " " + working[range_match.end() :]
        elif single_match:
            hour, minute = int(single_match.group(1)), int(single_match.group(2))
            if hour <= 23 and minute <= 59:
                base_date = date_local or now_local.date()
                start_local = _attach(datetime.combine(base_date, time(hour, minute)), now_local)
                end_local = start_local + timedelta(minutes=default_duration_minutes)
                date_local = base_date
                working = working[: single_match.start()] + " " + working[single_match.end() :]
        if start_local is None:
            for word, hour in _DAY_PART_HOURS.items():
                if word in working.lower():
                    base_date = date_local or now_local.date()
                    start_local = _attach(datetime.combine(base_date, time(hour, 0)), now_local)
                    end_local = start_local + timedelta(minutes=default_duration_minutes)
                    date_local = base_date
                    working = re.sub(re.escape(word), " ", working, flags=re.IGNORECASE)
                    break

    # 5.5. Время без даты в прошлом — это «завтра», а не «вчера» (правило «не тупи»).
    if start_local is not None and not date_specified and start_local <= now_local:
        start_local = start_local + timedelta(days=1)
        if end_local is not None:
            end_local = end_local + timedelta(days=1)
        date_local = start_local.date()

    # 6. Название = остаток.
    title = _clean(working)
    if not title:
        missing.append("title")
    if start_local is None:
        missing.append("time")
        # Дата без времени: подскажем её в мастере.
        if date_local is None:
            date_local = now_local.date()

    if repeat_rule == RepeatRule.WEEKLY.value and start_local is not None:
        repeat_rule = build_rule(
            RepeatRule.WEEKLY,
            {repeat_weekday if repeat_weekday is not None else start_local.weekday()},
        )

    return DraftEvent(
        title=title,
        date_local=date_local,
        start_local=start_local,
        end_local=end_local,
        repeat_rule=repeat_rule,
        category=category,
        category_custom_label=custom_label,
        reminder_offset=reminder_offset,
        reminder_specified=reminder_specified,
        date_specified=date_specified,
        missing=tuple(missing),
    )


def _drop_words(text: str, words: tuple[str, ...]) -> str:
    for word in words:
        text = re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    return text


def _drop_weekday(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return " " if match.group(0).lower() in _WEEKDAY_ALIASES else match.group(0)

    return re.sub(r"[a-zа-яё]+", replace, text, flags=re.IGNORECASE)


__all__ = [
    "DraftEvent",
    "parse_date_text",
    "parse_duration_text",
    "parse_event_text",
    "parse_interval_text",
    "parse_time_range_text",
    "parse_time_text",
]
