"""Inline-клавиатуры: всё ситуативное.

Callback-данные имеют вид ``namespace:action:arg`` и собираются здесь,
чтобы формат был один на весь проект.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from chronos.constants import (
    CB_ADD,
    CB_EVENT,
    CB_MENU_ADD,
    CB_MENU_MAIN,
    CB_MENU_REPORT,
    CB_MENU_SCHEDULE,
    CB_MENU_SETTINGS,
    CB_MENU_TIMER,
    CB_ONB,
    CB_SETTINGS,
    REMINDER_15_MIN,
    REMINDER_60_MIN,
    REMINDER_IMMEDIATE,
    REMINDER_OFF_TOKEN,
    ReportFrequency,
    TrackingMode,
)
from chronos.i18n import t
from chronos.services.schedule import Occurrence
from chronos.utils.timezones import COMMON_TIMEZONES


def callback(namespace: str, action: str, *args: object) -> str:
    """Собирает callback_data вида ``namespace:action:arg1:arg2``."""
    parts = [namespace, action, *(str(arg) for arg in args)]
    return ":".join(parts)


def parse_callback(data: str) -> tuple[str, str, list[str]]:
    """Разбирает callback_data на (namespace, action, args)."""
    parts = data.split(":")
    namespace = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    return namespace, action, parts[2:]


# ── Главное меню ──────────────────────────────────────────────────────────────


def main_menu_inline() -> InlineKeyboardMarkup:
    """Инлайн-меню по макету ТЗ (дублирует reply-кнопки для «одного тапа»)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("menu.btn_schedule"), callback_data=CB_MENU_SCHEDULE),
                InlineKeyboardButton(text=t("menu.btn_timer"), callback_data=CB_MENU_TIMER),
            ],
            [
                InlineKeyboardButton(text=t("menu.btn_add"), callback_data=CB_MENU_ADD),
                InlineKeyboardButton(text=t("menu.btn_report"), callback_data=CB_MENU_REPORT),
            ],
            [
                InlineKeyboardButton(text=t("menu.btn_settings"), callback_data=CB_MENU_SETTINGS),
            ],
        ]
    )


# ── Онбординг ─────────────────────────────────────────────────────────────────


def timezone_keyboard(prefix: str = CB_ONB, *, columns: int = 2) -> InlineKeyboardMarkup:
    """Зоны кнопками + «✏️ Другая» (docs/DECISIONS.md D-04)."""
    buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text=f"{option.emoji} {option.label}",
            callback_data=callback(prefix, "tz", index),
        )
        for index, option in enumerate(COMMON_TIMEZONES)
    ]
    rows: list[list[InlineKeyboardButton]] = [
        buttons[index : index + columns] for index in range(0, len(buttons), columns)
    ]
    rows.append(
        [InlineKeyboardButton(text=t("onboarding.tz_custom_button"), callback_data=callback(prefix, "tz", "custom"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tracking_mode_keyboard(prefix: str = CB_ONB) -> InlineKeyboardMarkup:
    """Режим трекинга: ручной / авто / оба."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("onboarding.mode_manual"),
                    callback_data=callback(prefix, "mode", TrackingMode.MANUAL.value),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.mode_auto"),
                    callback_data=callback(prefix, "mode", TrackingMode.AUTO.value),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.mode_both"),
                    callback_data=callback(prefix, "mode", TrackingMode.BOTH.value),
                )
            ],
        ]
    )


def work_hours_keyboard(prefix: str = CB_ONB) -> InlineKeyboardMarkup:
    """Пресеты рабочих часов + «свой вариант»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("onboarding.work_morning"), callback_data=callback(prefix, "work", "8-17")
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.work_day"), callback_data=callback(prefix, "work", "10-19")
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.work_evening"), callback_data=callback(prefix, "work", "12-21")
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.work_custom_button"),
                    callback_data=callback(prefix, "work", "custom"),
                )
            ],
        ]
    )


def skip_keyboard(namespace: str = CB_ADD) -> InlineKeyboardMarkup:
    """«Пропустить» / «Отмена» — правило «не тупи» действует везде."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common.skip"), callback_data=callback(namespace, "skip")
                ),
                InlineKeyboardButton(
                    text=t("common.cancel"), callback_data=callback(namespace, "cancel")
                ),
            ]
        ]
    )


# ── Добавление события ────────────────────────────────────────────────────────


def add_when_keyboard() -> InlineKeyboardMarkup:
    """Шаг «Когда?»: быстрые варианты + повтор + своя дата."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("add.when_today"), callback_data=callback(CB_ADD, "when", "today")),
                InlineKeyboardButton(text=t("add.when_tomorrow"), callback_data=callback(CB_ADD, "when", "tomorrow")),
            ],
            [
                InlineKeyboardButton(text=t("add.when_date"), callback_data=callback(CB_ADD, "when", "date")),
                InlineKeyboardButton(text=t("add.when_repeat_daily"), callback_data=callback(CB_ADD, "when", "daily")),
            ],
            [
                InlineKeyboardButton(
                    text=t("add.when_repeat_weekdays"), callback_data=callback(CB_ADD, "when", "weekdays")
                ),
                InlineKeyboardButton(
                    text=t("add.when_repeat_weekly"), callback_data=callback(CB_ADD, "when", "weekly")
                ),
            ],
            [InlineKeyboardButton(text=t("common.cancel"), callback_data=callback(CB_ADD, "cancel"))],
        ]
    )


def add_reminder_keyboard() -> InlineKeyboardMarkup:
    """Шаг «Напомнить»: в момент / за 15 / за час / не надо."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("add.reminder_immediate"),
                    callback_data=callback(CB_ADD, "remind", REMINDER_IMMEDIATE),
                ),
                InlineKeyboardButton(
                    text=t("add.reminder_15"),
                    callback_data=callback(CB_ADD, "remind", REMINDER_15_MIN),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("add.reminder_60"),
                    callback_data=callback(CB_ADD, "remind", REMINDER_60_MIN),
                ),
                InlineKeyboardButton(
                    text=t("add.reminder_off"),
                    callback_data=callback(CB_ADD, "remind", REMINDER_OFF_TOKEN),
                ),
            ],
            [InlineKeyboardButton(text=t("common.cancel"), callback_data=callback(CB_ADD, "cancel"))],
        ]
    )


def add_confirm_keyboard() -> InlineKeyboardMarkup:
    """Превью: подтвердить или начать заново."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("add.btn_confirm"), callback_data=callback(CB_ADD, "confirm")),
                InlineKeyboardButton(text=t("add.btn_restart"), callback_data=callback(CB_ADD, "restart")),
            ],
            [InlineKeyboardButton(text=t("common.cancel"), callback_data=callback(CB_ADD, "cancel"))],
        ]
    )


# ── Карточка события ──────────────────────────────────────────────────────────


def event_actions_keyboard(occurrence: Occurrence) -> InlineKeyboardMarkup:
    """Действия по событию: ✅ Иду / ⏰ Опоздаю / ❌ Отменяю / 🔄 Перенести."""
    date_key = occurrence.occurrence_date.isoformat()
    rows = [
        [
            InlineKeyboardButton(
                text=t("event.btn_going"),
                callback_data=callback(CB_EVENT, "go", occurrence.event_id, date_key),
            ),
            InlineKeyboardButton(
                text=t("event.btn_late"),
                callback_data=callback(CB_EVENT, "late", occurrence.event_id, date_key),
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("event.btn_cancel"),
                callback_data=callback(CB_EVENT, "cancel", occurrence.event_id, date_key),
            ),
            InlineKeyboardButton(
                text=t("event.btn_move"),
                callback_data=callback(CB_EVENT, "move", occurrence.event_id, date_key),
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("event.btn_timer"),
                callback_data=callback(CB_EVENT, "timer", occurrence.event_id, date_key),
            ),
            InlineKeyboardButton(
                text=t("event.btn_delete"),
                callback_data=callback(CB_EVENT, "delete", occurrence.event_id, date_key),
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_keyboard(reminder_id: int, event_id: int) -> InlineKeyboardMarkup:
    """Кнопки под напоминанием: «Да, старт» / «Нет» / «Позже»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("reminder.btn_yes"),
                    callback_data=callback("rem", "start", reminder_id, event_id),
                ),
                InlineKeyboardButton(
                    text=t("reminder.btn_no"),
                    callback_data=callback("rem", "no", reminder_id, event_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("reminder.btn_later"),
                    callback_data=callback("rem", "later", reminder_id, event_id),
                )
            ],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Одна кнопка «Назад» в меню — для тупиковых экранов."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("common.back"), callback_data=CB_MENU_MAIN)]
        ]
    )


def move_cancel_keyboard() -> InlineKeyboardMarkup:
    """Отмена переноса события (отдельный callback, чтобы не конфликтовать с карточкой)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common.cancel"), callback_data=callback(CB_EVENT, "move_cancel")
                )
            ]
        ]
    )


# ── Настройки ─────────────────────────────────────────────────────────────────


def settings_keyboard() -> InlineKeyboardMarkup:
    """Меню настроек: каждый пункт — подменю или ввод текста."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.btn_tz"), callback_data=callback(CB_SETTINGS, "tz")
                ),
                InlineKeyboardButton(
                    text=t("settings.btn_work"), callback_data=callback(CB_SETTINGS, "work")
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.btn_quiet"), callback_data=callback(CB_SETTINGS, "quiet")
                ),
                InlineKeyboardButton(
                    text=t("settings.btn_mode"), callback_data=callback(CB_SETTINGS, "mode")
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reports"), callback_data=callback(CB_SETTINGS, "reports")
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reset"), callback_data=callback(CB_SETTINGS, "reset")
                )
            ],
            [
                InlineKeyboardButton(text=t("common.back"), callback_data=CB_MENU_MAIN),
            ],
        ]
    )


def reports_frequency_keyboard() -> InlineKeyboardMarkup:
    """Частота отчётов: каждый вечер / раз в неделю / не присылать."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reports_daily"),
                    callback_data=callback(CB_SETTINGS, "reports", ReportFrequency.DAILY.value),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reports_weekly"),
                    callback_data=callback(CB_SETTINGS, "reports", ReportFrequency.WEEKLY.value),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reports_off"),
                    callback_data=callback(CB_SETTINGS, "reports", ReportFrequency.OFF.value),
                )
            ],
            [InlineKeyboardButton(text=t("common.back"), callback_data=callback(CB_SETTINGS, "back"))],
        ]
    )


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение необратимого удаления данных."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.btn_reset_yes"), callback_data=callback(CB_SETTINGS, "reset", "yes")
                ),
                InlineKeyboardButton(
                    text=t("settings.btn_reset_no"), callback_data=callback(CB_SETTINGS, "reset", "no")
                ),
            ]
        ]
    )


__all__ = [
    "add_confirm_keyboard",
    "add_reminder_keyboard",
    "add_when_keyboard",
    "back_to_menu_keyboard",
    "callback",
    "event_actions_keyboard",
    "main_menu_inline",
    "move_cancel_keyboard",
    "parse_callback",
    "reminder_keyboard",
    "reports_frequency_keyboard",
    "reset_confirm_keyboard",
    "settings_keyboard",
    "skip_keyboard",
    "timezone_keyboard",
    "tracking_mode_keyboard",
    "work_hours_keyboard",
]
