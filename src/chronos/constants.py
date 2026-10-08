"""Общие константы приложения.

Здесь живут только коды, ключи и числовые значения. Пользовательские тексты —
в пакете ``chronos.i18n`` (там же ключи для них). «Магических строк» в коде нет:
всё, что сравнивается или хранится, объявлено здесь.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from enum import StrEnum

# ── Приложение ────────────────────────────────────────────────────────────────

APP_NAME = "Хронос"
APP_SLUG = "chronos"
DEFAULT_LOCALE = "ru"
SUPPORTED_LOCALES = ("ru",)

# ── Категории трекинга ────────────────────────────────────────────────────────


class Category(StrEnum):
    """Категории записей времени. Ключ хранится в БД, emoji и подпись — для UI."""

    WORK = "work"
    STUDY = "study"
    SOCIAL = "social"
    FOOD = "food"
    REST = "rest"
    SPORT = "sport"
    BREAK = "break"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class CategoryMeta:
    """Отображение категории: emoji, подпись, фокусная ли (см. docs/DECISIONS.md D-03)."""

    emoji: str
    label: str
    is_focus: bool


CATEGORY_META: dict[Category, CategoryMeta] = {
    Category.WORK: CategoryMeta("💼", "Работа", True),
    Category.STUDY: CategoryMeta("📚", "Учёба", True),
    Category.SOCIAL: CategoryMeta("📱", "Соцсети", False),
    Category.FOOD: CategoryMeta("🍔", "Еда", False),
    Category.REST: CategoryMeta("😴", "Отдых", False),
    Category.SPORT: CategoryMeta("🏃", "Спорт", False),
    Category.BREAK: CategoryMeta("🚶", "Перерыв", False),
    Category.CUSTOM: CategoryMeta("✏️", "Своя метка", False),
}

#: Порядок кнопок в клавиатурах: сначала фокусные, потом остальные.
CATEGORY_ORDER: tuple[Category, ...] = (
    Category.WORK,
    Category.STUDY,
    Category.SPORT,
    Category.SOCIAL,
    Category.FOOD,
    Category.REST,
    Category.BREAK,
    Category.CUSTOM,
)

#: Категория для событий расписания без явной метки.
UNCATEGORIZED_LABEL = "Без категории"
UNCATEGORIZED_EMOJI = "🗂"


def category_emoji(category: str | None) -> str:
    """Только emoji категории (для карточек и заголовков)."""
    if not category:
        return UNCATEGORIZED_EMOJI
    try:
        return CATEGORY_META[Category(category)].emoji
    except ValueError:
        return CATEGORY_META[Category.CUSTOM].emoji


def category_label(category: str | None) -> str:
    """Человекочитаемая подпись категории с emoji (или «Без категории»)."""
    if not category:
        return f"{UNCATEGORIZED_EMOJI} {UNCATEGORIZED_LABEL}"
    try:
        meta = CATEGORY_META[Category(category)]
    except ValueError:
        # Свободная метка пользователя (см. Category.CUSTOM).
        return f"{CATEGORY_META[Category.CUSTOM].emoji} {category}"
    return f"{meta.emoji} {meta.label}"


#: Синонимы категорий из текста и хэштегов: «#работа», «#учёба», «#work».
CATEGORY_ALIASES: dict[str, str] = {
    "работа": Category.WORK.value,
    "work": Category.WORK.value,
    "работе": Category.WORK.value,
    "учеба": Category.STUDY.value,
    "учёба": Category.STUDY.value,
    "study": Category.STUDY.value,
    "учебу": Category.STUDY.value,
    "соцсети": Category.SOCIAL.value,
    "social": Category.SOCIAL.value,
    "еда": Category.FOOD.value,
    "food": Category.FOOD.value,
    "обед": Category.FOOD.value,
    "отдых": Category.REST.value,
    "rest": Category.REST.value,
    "спорт": Category.SPORT.value,
    "sport": Category.SPORT.value,
    "перерыв": Category.BREAK.value,
    "break": Category.BREAK.value,
    "своя": Category.CUSTOM.value,
    "custom": Category.CUSTOM.value,
}


def resolve_category(text: str | None) -> tuple[str | None, str | None]:
    """Разбирает метку в (ключ категории, своя подпись).

    Для известных категорий подпись равна None, для свободной метки — сам текст
    (подпись показывается пользователю, ключ хранится в БД).
    """
    if not text:
        return None, None
    cleaned = text.strip().lstrip("#")
    if not cleaned:
        return None, None
    known = CATEGORY_ALIASES.get(cleaned.lower())
    if known is not None:
        return known, None
    return cleaned, cleaned


def is_focus_category(category: str | None, *, custom_is_focus: bool = False) -> bool:
    """Является ли категория фокусной для метрик продуктивности."""
    if not category:
        return False
    try:
        return CATEGORY_META[Category(category)].is_focus
    except ValueError:
        return custom_is_focus


# ── Способы трекинга ──────────────────────────────────────────────────────────


class TrackingMode(StrEnum):
    """Режим трекинга времени (docs/DECISIONS.md D-02, I-01)."""

    MANUAL = "manual"  # только кнопки «Старт/Стоп»
    AUTO = "auto"  # только пассивные/контекстные опросы
    BOTH = "both"  # и таймер, и опросы

    @property
    def allows_timer(self) -> bool:
        return self is not TrackingMode.AUTO

    @property
    def allows_polls(self) -> bool:
        return self is not TrackingMode.MANUAL


# ── Источники записей времени ─────────────────────────────────────────────────


class LogSource(StrEnum):
    """Откуда взялась запись времени."""

    MANUAL = "manual"
    TIMER = "timer"
    POLL = "poll"
    DIGEST = "digest"
    AUTO = "auto"


# ── Статусы событий ───────────────────────────────────────────────────────────


class EventStatus(StrEnum):
    """Статус события расписания."""

    PLANNED = "planned"
    GOING = "going"  # ✅ Иду
    LATE = "late"  # ⏰ Опоздаю
    CANCELED = "canceled"  # ❌ Отменяю
    MOVED = "moved"  # 🔄 Перенести
    DONE = "done"

    @property
    def counts_as_plan(self) -> bool:
        """Входит ли событие в «план» отчёта (см. docs/DECISIONS.md D-10)."""
        return self not in (EventStatus.CANCELED, EventStatus.MOVED)


# ── Повторяемость событий (подмножество RFC 5545, см. D-07) ───────────────────


class RepeatRule(StrEnum):
    """Базовое правило повтора. Дни для недельного — в хвосте: ``weekly:MO,WE``."""

    NONE = "none"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"


#: Коды дней недели (RFC 5545) в порядке ISO: понедельник первый.
WEEKDAY_CODES: tuple[str, ...] = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
#: Короткие русские подписи для UI.
WEEKDAY_RU: dict[str, str] = {
    "MO": "пн",
    "TU": "вт",
    "WE": "ср",
    "TH": "чт",
    "FR": "пт",
    "SA": "сб",
    "SU": "вс",
}
#: Полные русские подписи (для дат и заголовков).
WEEKDAY_RU_FULL: tuple[str, ...] = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
#: Месяцы в родительном падеже: «12 мая».
MONTH_RU_GENITIVE: tuple[str, ...] = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
#: Префикс недельного правила: ``weekly:MO,WE``.
REPEAT_WEEKLY_PREFIX = "weekly:"

# ── Напоминания ───────────────────────────────────────────────────────────────


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    CANCELED = "canceled"


#: Значение «напоминать не надо».
REMINDER_OFF: int | None = None
#: Токен кнопки «Не надо» в callback-данных (None в строку не превращается).
REMINDER_OFF_TOKEN = "off"
#: Смещения напоминания в минутах до начала события.
REMINDER_IMMEDIATE = 0
REMINDER_15_MIN = 15
REMINDER_60_MIN = 60
REMINDER_CHOICES: tuple[int | None, ...] = (
    REMINDER_IMMEDIATE,
    REMINDER_15_MIN,
    REMINDER_60_MIN,
    REMINDER_OFF,
)
DEFAULT_REMINDER_OFFSET_MIN = REMINDER_15_MIN

# ── Опросы ────────────────────────────────────────────────────────────────────


class PollKind(StrEnum):
    PASSIVE = "passive"  # раз в час в рабочие часы
    CONTEXTUAL = "contextual"  # событие по плану, а таймер молчит


class PollStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    EXPIRED = "expired"


#: Специальные ответы на пассивный опрос.
POLL_ANSWER_SAME_AS_LAST = "__same__"
POLL_ANSWER_SKIP = "__skip__"

# ── Настройки (таблица settings) ──────────────────────────────────────────────


class SettingKey(StrEnum):
    """Ключи «мягких» настроек в key-value таблице (docs/DECISIONS.md D-02)."""

    REPORT_FREQUENCY = "report_frequency"
    MUTE_UNTIL = "mute_until"
    DIGEST_MORNING = "digest_morning"
    DIGEST_EVENING = "digest_evening"
    REMINDERS_ENABLED = "reminders_enabled"


class ReportFrequency(StrEnum):
    OFF = "off"
    DAILY = "daily"
    WEEKLY = "weekly"


ON = "on"
OFF = "off"

# ── Значения по умолчанию (ТЗ, раздел 2/4) ────────────────────────────────────

DEFAULT_QUIET_START = time(23, 0)
DEFAULT_QUIET_END = time(8, 0)
DEFAULT_WORK_START = time(10, 0)
DEFAULT_WORK_END = time(19, 0)
DEFAULT_MORNING_DIGEST_AT = time(8, 0)
DEFAULT_EVENING_DIGEST_AT = time(20, 30)
DEFAULT_AUTOSTOP_AT = time(23, 0)
DEFAULT_WEEKLY_REPORT_AT = time(9, 0)

#: Разовое событие без указанного конца длится столько минут.
DEFAULT_EVENT_MINUTES = 60
#: На сколько дней вперёд материализуем напоминания повторяющихся событий.
DEFAULT_REMINDER_HORIZON_DAYS = 7

#: Минимальная длина записи времени; более короткие не пишем (случайные тапы).
MIN_LOG_MINUTES = 1
#: Если таймер идёт дольше — спрашиваем «всё ещё работаешь?».
IDLE_TIMER_AFTER = timedelta(hours=3)
#: Таймер, идущий дольше этого срока, при автостопе подрезается (сон/забыл).
MAX_LOG_HOURS = 16

# ── UX-константы ──────────────────────────────────────────────────────────────

TOAST_TTL_SECONDS = 5
CALLBACK_DEDUP_WINDOW = timedelta(milliseconds=1200)
POLL_INTERVAL = timedelta(hours=1)

# ── Callback-данные (namespace:action:arg) ────────────────────────────────────

CB_SEP = ":"
CB_MENU = "menu"
CB_MENU_MAIN = "menu:main"
CB_MENU_SCHEDULE = "menu:schedule"
CB_MENU_TIMER = "menu:timer"
CB_MENU_ADD = "menu:add"
CB_MENU_REPORT = "menu:report"
CB_MENU_SETTINGS = "menu:settings"
CB_NOOP = "noop"

CB_ONB = "onb"  # онбординг
CB_ADD = "add"  # мастер добавления
CB_EVENT = "ev"  # действия по событию
CB_REPORT = "rep"
CB_SETTINGS = "set"
CB_TIMER = "tmr"
CB_POLL = "poll"
