"""FSM-состояния сценариев бота.

Состояния описывают «где мы в диалоге», вся логика — в сервисах.
Хранилище FSM — MemoryStorage: для single-user MVP этого достаточно,
для мультиюзера меняется одной строкой в ``bot/dispatcher.py``.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """Привет → таймзона → режим трекинга → рабочие часы → готово."""

    timezone = State()
    timezone_custom = State()
    mode = State()
    work_hours = State()
    work_hours_custom = State()


class AddEvent(StatesGroup):
    """Пошаговое добавление события: название → когда → время → напоминание → превью."""

    title = State()
    when = State()
    when_custom = State()
    time = State()
    reminder = State()
    confirm = State()


class MoveEvent(StatesGroup):
    """Перенос одного вхождения: ждём новое время текстом."""

    waiting_time = State()


class SettingsFlow(StatesGroup):
    """Правка настроек: пользователь ввёл значение текстом."""

    timezone = State()
    work_hours = State()
    quiet_hours = State()


__all__ = ["AddEvent", "MoveEvent", "Onboarding", "SettingsFlow"]
