"""Сценарий онбординга: привет → таймзона → режим трекинга → рабочие часы → готово.

Цель ТЗ — первое действие пользователя за ≤ 60 секунд, поэтому три шага
из четырёх закрываются одним тапом по кнопке.
"""

from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import safe_answer, show
from chronos.bot.keyboards.inline import (
    callback,
    parse_callback,
    skip_keyboard,
    timezone_keyboard,
    tracking_mode_keyboard,
    work_hours_keyboard,
)
from chronos.bot.keyboards.reply import main_menu_keyboard
from chronos.bot.states import Onboarding
from chronos.constants import CB_ONB, TrackingMode
from chronos.i18n import t
from chronos.models import User
from chronos.services import users as users_service
from chronos.utils.datetime_parser import parse_interval_text
from chronos.utils.timezones import COMMON_TIMEZONES, resolve_timezone, tz_for, tz_name

router = Router(name="onboarding")

TOTAL_STEPS = 3
_DEFAULT_WORK_PRESETS: dict[str, tuple[time, time]] = {
    "8-17": (time(8, 0), time(17, 0)),
    "10-19": (time(10, 0), time(19, 0)),
    "12-21": (time(12, 0), time(21, 0)),
}


def _step(step: int, body: str) -> str:
    """Заголовок «Шаг N из 3» + тело шага."""
    return f"{t('onboarding.step', step=step, total=TOTAL_STEPS)}\n\n{body}"


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    now_utc,
) -> None:
    """``/start``: первый запуск — онбординг, дальше — меню (docs/DECISIONS.md D-01)."""
    if user.is_onboarded:
        from chronos.bot.handlers.menu import render_menu_message

        await render_menu_message(message, session=session, user=user, now_utc=now_utc)
        return

    await state.set_state(Onboarding.timezone)
    await message.answer(
        _step(
            1,
            "\n\n".join(
                [t("onboarding.greeting"), t("onboarding.tz_title"), t("onboarding.tz_hint")]
            ),
        ),
        reply_markup=timezone_keyboard(CB_ONB),
    )


@router.callback_query(Onboarding.timezone, F.data.startswith(f"{CB_ONB}:tz:"))
async def choose_timezone(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Выбор зоны кнопкой или переход к ручному вводу."""
    _, _, args = parse_callback(query.data or "")
    value = args[0] if args else ""
    if value == "custom":
        await state.set_state(Onboarding.timezone_custom)
        await show(query, _step(1, t("onboarding.tz_custom_prompt")), markup=skip_keyboard(CB_ONB))
        await safe_answer(query)
        return

    try:
        zone_name = COMMON_TIMEZONES[int(value)].iana
    except (ValueError, IndexError):
        await query.answer(t("onboarding.tz_unknown"), show_alert=True)
        return

    await users_service.set_timezone(session, user, zone_name)
    await _goto_mode(query, state, note=t("onboarding.tz_saved", tz=tz_name(tz_for(zone_name))))


@router.message(Onboarding.timezone_custom, F.text)
async def custom_timezone(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Ручной ввод зоны: «Москва», «Asia/Almaty», «UTC+3»."""
    zone = resolve_timezone(message.text)
    if zone is None:
        await message.answer(t("onboarding.tz_unknown"))
        return
    await users_service.set_timezone(session, user, tz_name(zone))
    await state.set_state(Onboarding.mode)
    await message.answer(
        _step(2, "\n\n".join([t("onboarding.mode_title"), t("onboarding.mode_hint")])),
        reply_markup=tracking_mode_keyboard(CB_ONB),
    )


async def _goto_mode(query: CallbackQuery, state: FSMContext, *, note: str | None = None) -> None:
    """Переход к шагу «режим трекинга»."""
    await state.set_state(Onboarding.mode)
    body = "\n\n".join([t("onboarding.mode_title"), t("onboarding.mode_hint")])
    text = _step(2, body)
    if note:
        text = f"{note}\n\n{text}"
    await show(query, text, markup=tracking_mode_keyboard(CB_ONB))
    await safe_answer(query)


@router.callback_query(Onboarding.mode, F.data.startswith(f"{CB_ONB}:mode:"))
async def choose_mode(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Режим трекинга: ручной / авто / оба."""
    _, _, args = parse_callback(query.data or "")
    try:
        mode = TrackingMode(args[0])
    except (ValueError, IndexError):
        await query.answer(t("common.error_generic_cb"), show_alert=True)
        return

    await users_service.set_tracking_mode(session, user, mode)
    await state.set_state(Onboarding.work_hours)
    body = "\n\n".join([t("onboarding.work_title"), t("onboarding.work_hint")])
    await show(
        query,
        f"{t('onboarding.mode_saved', mode=_mode_label(mode))}\n\n{_step(3, body)}",
        markup=work_hours_keyboard(CB_ONB),
    )
    await safe_answer(query)


@router.callback_query(Onboarding.work_hours, F.data.startswith(f"{CB_ONB}:work:"))
async def choose_work_hours(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, now_utc
) -> None:
    """Рабочие часы пресетом или вручную."""
    _, _, args = parse_callback(query.data or "")
    value = args[0] if args else ""
    if value == "custom":
        await state.set_state(Onboarding.work_hours_custom)
        await show(query, _step(3, t("onboarding.work_custom_prompt")), markup=skip_keyboard(CB_ONB))
        await safe_answer(query)
        return

    preset = _DEFAULT_WORK_PRESETS.get(value)
    if preset is None:
        await query.answer(t("common.error_generic_cb"), show_alert=True)
        return

    await users_service.set_work_hours(session, user, preset[0], preset[1])
    await _finish(query, state, session, user, now_utc=now_utc)


@router.message(Onboarding.work_hours_custom, F.text)
async def custom_work_hours(
    message: Message, state: FSMContext, session: AsyncSession, user: User, now_utc
) -> None:
    """Ручной ввод рабочих часов: «9:30-18:00»."""
    interval = parse_interval_text(message.text)
    if interval is None:
        await message.answer(t("settings.interval_bad"))
        return
    await users_service.set_work_hours(session, user, interval[0], interval[1])
    await _finish_message(message, state, session, user, now_utc=now_utc)


@router.callback_query(StateFilter(Onboarding), F.data == callback(CB_ONB, "skip"))
async def skip_step(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, now_utc
) -> None:
    """«Пропустить»: оставляем значения по умолчанию и идём дальше."""
    current = await state.get_state()
    if current == Onboarding.timezone_custom.state:
        await _goto_mode(query, state)
        return
    await _finish(query, state, session, user, now_utc=now_utc)


@router.callback_query(StateFilter(Onboarding), F.data == callback(CB_ONB, "cancel"))
async def cancel_onboarding(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """«Отмена» на шаге ввода: возвращаем выбор кнопками."""
    current = await state.get_state()
    await safe_answer(query)
    if current == Onboarding.timezone_custom.state:
        await state.set_state(Onboarding.timezone)
        await show(query, _step(1, t("onboarding.tz_title")), markup=timezone_keyboard(CB_ONB))
        return
    await state.set_state(Onboarding.work_hours)
    await show(query, _step(3, t("onboarding.work_title")), markup=work_hours_keyboard(CB_ONB))


async def _finish(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, *, now_utc
) -> None:
    """Завершение онбординга из callback-сценария.

    Мастер-сообщение удаляем: в чате остаются только «Готово» с reply-клавиатурой
    и главное меню — без визуального мусора.
    """
    await users_service.finish_onboarding(session, user)
    await state.clear()
    await safe_answer(query)
    await _safe_delete(query.message)
    await query.bot.send_message(
        user.telegram_id, _step(3, t("onboarding.done")), reply_markup=main_menu_keyboard()
    )
    from chronos.bot.handlers.menu import render_menu_message

    await render_menu_message(
        query.bot, session=session, user=user, now_utc=now_utc, chat_id=user.telegram_id
    )


async def _safe_delete(message: Message | None) -> None:
    """Удаляет сообщение, если оно доступно (иначе молча пропускаем)."""
    if message is None:
        return
    try:
        await message.delete()
    except Exception:  # pragma: no cover - сообщение могло быть удалено вручную
        return


async def _finish_message(
    message: Message, state: FSMContext, session: AsyncSession, user: User, *, now_utc
) -> None:
    """Завершение онбординга из текстового сценария."""
    await users_service.finish_onboarding(session, user)
    await state.clear()
    await message.answer(
        _step(3, t("onboarding.done")), reply_markup=main_menu_keyboard()
    )
    from chronos.bot.handlers.menu import render_menu_message

    await render_menu_message(message, session=session, user=user, now_utc=now_utc)


def _mode_label(mode: TrackingMode) -> str:
    """Подпись режима трекинга для сообщений."""
    return {
        TrackingMode.MANUAL: t("onboarding.mode_manual"),
        TrackingMode.AUTO: t("onboarding.mode_auto"),
        TrackingMode.BOTH: t("onboarding.mode_both"),
    }[mode]


__all__ = ["router"]
