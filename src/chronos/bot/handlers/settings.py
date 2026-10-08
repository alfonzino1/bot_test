"""Настройки: инлайн-меню, где каждый пункт — подменю или ввод текстом.

Модуль D ТЗ: таймзона, рабочие часы, тихий час, режим трекинга, частота
отчётов, сброс данных. Источник правды — колонки ``users`` + таблица ``settings``
(docs/DECISIONS.md D-02).
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import show, toast
from chronos.bot.keyboards.inline import (
    callback,
    parse_callback,
    reports_frequency_keyboard,
    reset_confirm_keyboard,
    settings_keyboard,
    timezone_keyboard,
    tracking_mode_keyboard,
)
from chronos.bot.states import SettingsFlow
from chronos.constants import (
    CB_MENU_SETTINGS,
    CB_SETTINGS,
    OFF,
    ReportFrequency,
    TrackingMode,
)
from chronos.i18n import t
from chronos.models import User
from chronos.services import users as users_service
from chronos.services.users import UserSettings
from chronos.utils.datetime_parser import parse_interval_text
from chronos.utils.formatting import format_time, humanize_datetime
from chronos.utils.timezones import COMMON_TIMEZONES, resolve_timezone, tz_for, tz_name

router = Router(name="settings")


def render_settings(cfg: UserSettings, user: User, *, now_utc: datetime) -> str:
    """Текст экрана настроек: текущие значения + что можно менять."""
    reports = {
        ReportFrequency.OFF: t("settings.reports_off"),
        ReportFrequency.DAILY: t("settings.reports_daily"),
        ReportFrequency.WEEKLY: t("settings.reports_weekly"),
    }[cfg.report_frequency]
    tz = tz_for(user.tz)
    if cfg.muted_until is not None and cfg.muted_until > now_utc:
        mute = t(
            "settings.mute_until",
            until=humanize_datetime(cfg.muted_until.astimezone(tz), now_utc.astimezone(tz)),
        )
    else:
        mute = t("settings.mute_off")
    body = t(
        "settings.body",
        tz=cfg.tz,
        work_start=format_time(cfg.work_start),
        work_end=format_time(cfg.work_end),
        quiet_start=format_time(cfg.quiet_start),
        quiet_end=format_time(cfg.quiet_end),
        mode=mode_label(cfg.tracking_mode),
        reports=reports,
        mute=mute,
    )
    return f"{t('settings.title')}\n\n{body}"


def mode_label(mode: TrackingMode) -> str:
    """Подпись режима трекинга."""
    return {
        TrackingMode.MANUAL: t("onboarding.mode_manual"),
        TrackingMode.AUTO: t("onboarding.mode_auto"),
        TrackingMode.BOTH: t("onboarding.mode_both"),
    }[mode]


async def show_settings(
    query: CallbackQuery, session: AsyncSession, user: User, *, now_utc: datetime
) -> None:
    """Показывает главный экран настроек."""
    cfg = await users_service.get_settings(session, user)
    await show(query, render_settings(cfg, user, now_utc=now_utc), markup=settings_keyboard())


@router.callback_query(F.data == CB_MENU_SETTINGS)
async def open_settings(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Кнопка «⚙️ Настройки»."""
    await query.answer()
    await show_settings(query, session, user, now_utc=now_utc)


@router.callback_query(F.data == callback(CB_SETTINGS, "back"))
async def back_to_settings(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Возврат на главный экран настроек."""
    await query.answer()
    await show_settings(query, session, user, now_utc=now_utc)


# ── Таймзона ──────────────────────────────────────────────────────────────────


@router.callback_query(F.data == callback(CB_SETTINGS, "tz"))
async def ask_timezone(query: CallbackQuery) -> None:
    """Показывает кнопки зон."""
    await query.answer()
    await show(query, t("onboarding.tz_title"), markup=timezone_keyboard(CB_SETTINGS))


@router.callback_query(F.data.startswith(f"{CB_SETTINGS}:tz:"))
async def set_timezone(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Сохраняет выбранную зону или просит ввести её текстом."""
    _, _, args = parse_callback(query.data or "")
    value = args[0] if args else ""
    if value == "custom":
        await state.set_state(SettingsFlow.timezone)
        await show(query, t("settings.ask_tz"), markup=None)
        return
    try:
        zone_name = COMMON_TIMEZONES[int(value)].iana
    except (ValueError, IndexError):
        await toast(query, t("onboarding.tz_unknown"), alert=True)
        return
    await users_service.set_timezone(session, user, zone_name)
    await toast(query, t("settings.saved"))
    await show_settings(query, session, user, now_utc=now_utc)


@router.message(SettingsFlow.timezone, F.text)
async def set_timezone_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Текстовый ввод зоны в настройках."""
    zone = resolve_timezone(message.text)
    if zone is None:
        await message.answer(t("onboarding.tz_unknown"))
        return
    await users_service.set_timezone(session, user, tz_name(zone))
    await state.clear()
    cfg = await users_service.get_settings(session, user)
    await message.answer(render_settings(cfg, user, now_utc=now_utc), reply_markup=settings_keyboard())


# ── Рабочие часы и тихий час ──────────────────────────────────────────────────


@router.callback_query(F.data == callback(CB_SETTINGS, "work"))
async def ask_work_hours(query: CallbackQuery, state: FSMContext) -> None:
    """Просит ввести рабочие часы текстом."""
    await state.set_state(SettingsFlow.work_hours)
    await query.answer()
    await show(query, t("settings.ask_work"), markup=None)


@router.message(SettingsFlow.work_hours, F.text)
async def set_work_hours_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """«9:30-18:00» → рабочие часы."""
    interval = parse_interval_text(message.text)
    if interval is None:
        await message.answer(t("settings.interval_bad"))
        return
    await users_service.set_work_hours(session, user, interval[0], interval[1])
    await state.clear()
    cfg = await users_service.get_settings(session, user)
    await message.answer(render_settings(cfg, user, now_utc=now_utc), reply_markup=settings_keyboard())


@router.callback_query(F.data == callback(CB_SETTINGS, "quiet"))
async def ask_quiet_hours(query: CallbackQuery, state: FSMContext) -> None:
    """Просит ввести тихий час текстом."""
    await state.set_state(SettingsFlow.quiet_hours)
    await query.answer()
    await show(query, t("settings.ask_quiet"), markup=None)


@router.message(SettingsFlow.quiet_hours, F.text)
async def set_quiet_hours_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """«23:00-8:00» → тихий час (может идти через полночь)."""
    interval = parse_interval_text(message.text)
    if interval is None:
        await message.answer(t("settings.interval_bad"))
        return
    await users_service.set_quiet_hours(session, user, interval[0], interval[1])
    await state.clear()
    cfg = await users_service.get_settings(session, user)
    await message.answer(render_settings(cfg, user, now_utc=now_utc), reply_markup=settings_keyboard())


# ── Режим трекинга ────────────────────────────────────────────────────────────


@router.callback_query(F.data == callback(CB_SETTINGS, "mode"))
async def ask_mode(query: CallbackQuery) -> None:
    """Показывает выбор режима трекинга."""
    await query.answer()
    await show(query, t("settings.ask_mode"), markup=tracking_mode_keyboard(CB_SETTINGS))


@router.callback_query(F.data.startswith(f"{CB_SETTINGS}:mode:"))
async def set_mode(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Сохраняет режим трекинга."""
    _, _, args = parse_callback(query.data or "")
    try:
        mode = TrackingMode(args[0])
    except (ValueError, IndexError):
        await toast(query, t("common.error_generic_cb"), alert=True)
        return
    await users_service.set_tracking_mode(session, user, mode)
    await toast(query, t("settings.saved"))
    await show_settings(query, session, user, now_utc=now_utc)


# ── Отчёты ────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == callback(CB_SETTINGS, "reports"))
async def ask_reports(query: CallbackQuery) -> None:
    """Показывает выбор частоты отчётов."""
    await query.answer()
    await show(query, t("settings.ask_reports"), markup=reports_frequency_keyboard())


@router.callback_query(F.data.startswith(f"{CB_SETTINGS}:reports:"))
async def set_reports(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Сохраняет частоту отчётов."""
    _, _, args = parse_callback(query.data or "")
    try:
        frequency = ReportFrequency(args[0])
    except (ValueError, IndexError):
        await toast(query, t("common.error_generic_cb"), alert=True)
        return
    await users_service.set_report_frequency(session, user, frequency)
    await toast(query, t("settings.saved"))
    await show_settings(query, session, user, now_utc=now_utc)


# ── Сброс данных ──────────────────────────────────────────────────────────────


@router.callback_query(F.data == callback(CB_SETTINGS, "reset"))
async def ask_reset(query: CallbackQuery) -> None:
    """Спрашивает подтверждение перед необратимым удалением."""
    await query.answer()
    await show(query, t("settings.reset_confirm"), markup=reset_confirm_keyboard())


@router.callback_query(F.data.startswith(f"{CB_SETTINGS}:reset:"))
async def do_reset(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Удаляет все данные пользователя или отменяет действие."""
    _, _, args = parse_callback(query.data or "")
    if (args[0] if args else "") != "yes":
        await query.answer(t("common.canceled"))
        await show_settings(query, session, user, now_utc=now_utc)
        return
    await users_service.reset_all_data(session, user)
    await query.answer(t("settings.reset_done"))
    await show(query, t("settings.reset_done"), markup=None)


__all__ = ["mode_label", "render_settings", "router", "show_settings"]
