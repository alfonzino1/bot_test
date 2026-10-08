"""Сценарии добавления события: быстрый `/add` и пошаговый мастер.

Быстрый путь: ``/add Встреча завтра 15:00-16:00 #работа`` → превью → «Ок».
Пошаговый путь включается кнопкой «➕ Добавить»: название → когда → во сколько →
напомнить → превью → «Ок» (ТЗ, раздел 4).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import safe_answer, show, toast
from chronos.bot.keyboards.inline import (
    add_confirm_keyboard,
    add_reminder_keyboard,
    add_when_keyboard,
    callback,
    event_actions_keyboard,
    parse_callback,
    skip_keyboard,
)
from chronos.bot.states import AddEvent
from chronos.constants import (
    CB_ADD,
    CB_MENU_ADD,
    EventStatus,
    REMINDER_OFF,
    REMINDER_OFF_TOKEN,
    RepeatRule,
)
from chronos.i18n import t
from chronos.logging_setup import logger
from chronos.models import User
from chronos.services import schedule as schedule_service
from chronos.services.drafts import DraftState
from chronos.utils.datetime_parser import parse_date_text, parse_event_text, parse_time_range_text
from chronos.utils.formatting import format_time, format_when
from chronos.utils.recurrence import build_rule
from chronos.utils.timezones import tz_for

router = Router(name="add")


# ── Точки входа ───────────────────────────────────────────────────────────────


@router.message(Command("add"))
async def handle_add_command(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    now_utc: datetime,
) -> None:
    """``/add`` без текста — мастер; ``/add <строка>`` — быстрое добавление."""
    raw = (command.args or "").strip()
    if not raw:
        await _ask_title(message, state)
        return

    now_local = now_utc.astimezone(tz_for(user.tz))
    parsed = parse_event_text(raw, now_local=now_local)
    if "title" in parsed.missing:
        await message.answer(f"{t('common.not_understood')}\n\n{t('add.usage')}")
        return

    draft = DraftState.from_draft(parsed)
    await _store(state, draft)
    if "time" in parsed.missing:
        await state.set_state(AddEvent.time)
        await message.answer(
            f"✍️ {draft.title}\n\n{t('add.time_prompt')}\n{t('add.time_prompt_hint')}",
            reply_markup=skip_keyboard(CB_ADD),
        )
        return
    await _show_preview(message, state, draft, now_local=now_local)


@router.callback_query(F.data == CB_MENU_ADD)
async def handle_add_button(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Кнопка «➕ Добавить» открывает мастер прямо в текущем сообщении."""
    await safe_answer(query)
    await state.set_state(AddEvent.title)
    await state.update_data({DraftState.STATE_KEY: DraftState().to_state()})
    await show(
        query,
        f"{t('add.wizard_title')}\n{t('add.wizard_title_hint')}",
        markup=skip_keyboard(CB_ADD),
    )


async def _ask_title(message: Message, state: FSMContext) -> None:
    """Первый шаг мастера: название события."""
    await state.set_state(AddEvent.title)
    await state.update_data({DraftState.STATE_KEY: DraftState().to_state()})
    await message.answer(
        f"{t('add.wizard_title')}\n{t('add.wizard_title_hint')}",
        reply_markup=skip_keyboard(CB_ADD),
    )


# ── Шаг 1: название ───────────────────────────────────────────────────────────


@router.message(AddEvent.title, F.text)
async def step_title(message: Message, state: FSMContext) -> None:
    """Пользователь ввёл название — спрашиваем «когда»."""
    draft = await _load(state)
    draft = draft.with_title(message.text or "")
    await _store(state, draft)
    await state.set_state(AddEvent.when)
    await message.answer(t("add.wizard_when"), reply_markup=add_when_keyboard())


# ── Шаг 2: когда ──────────────────────────────────────────────────────────────


@router.callback_query(AddEvent.when, F.data.startswith(f"{CB_ADD}:when:"))
async def step_when(
    query: CallbackQuery, state: FSMContext, user: User, now_utc: datetime
) -> None:
    """Быстрые варианты даты и повтора."""
    _, _, args = parse_callback(query.data or "")
    preset = args[0] if args else ""
    now_local = now_utc.astimezone(tz_for(user.tz))
    draft = await _load(state)

    if preset == "today":
        draft = draft.with_date(now_local.date())
    elif preset == "tomorrow":
        draft = draft.with_date(now_local.date() + timedelta(days=1))
    elif preset == "date":
        await _store(state, draft)
        await state.set_state(AddEvent.when_custom)
        await show(query, t("add.when_date_prompt"), markup=skip_keyboard(CB_ADD))
        await safe_answer(query)
        return
    elif preset == "daily":
        draft = draft.with_date(draft.day or now_local.date()).with_repeat(RepeatRule.DAILY.value)
    elif preset == "weekdays":
        draft = draft.with_date(draft.day or now_local.date()).with_repeat(RepeatRule.WEEKDAYS.value)
    elif preset == "weekly":
        day = draft.day or now_local.date()
        draft = draft.with_date(day).with_repeat(build_rule(RepeatRule.WEEKLY, {day.weekday()}))
    else:
        await toast(query, t("common.error_generic_cb"), alert=True)
        return

    await _store(state, draft)
    await state.set_state(AddEvent.time)
    await show(
        query,
        f"{t('add.time_prompt')}\n{t('add.time_prompt_hint')}",
        markup=skip_keyboard(CB_ADD),
    )
    await safe_answer(query)


@router.message(AddEvent.when_custom, F.text)
async def step_when_custom(
    message: Message, state: FSMContext, user: User, now_utc: datetime
) -> None:
    """Своя дата: «12.05», «через 3 дня», «пт»."""
    now_local = now_utc.astimezone(tz_for(user.tz))
    day = parse_date_text(message.text, now_local=now_local)
    if day is None:
        await message.answer(t("add.when_bad"))
        return
    draft = (await _load(state)).with_date(day)
    await _store(state, draft)
    await state.set_state(AddEvent.time)
    await message.answer(
        f"{t('add.time_prompt')}\n{t('add.time_prompt_hint')}",
        reply_markup=skip_keyboard(CB_ADD),
    )


# ── Шаг 3: во сколько ─────────────────────────────────────────────────────────


@router.message(AddEvent.time, F.text)
async def step_time(
    message: Message, state: FSMContext, user: User, now_utc: datetime
) -> None:
    """Время текстом: «15:00» или «15:00-16:30»."""
    now_local = now_utc.astimezone(tz_for(user.tz))
    draft = await _load(state)
    on_date = draft.day or now_local.date()
    interval = parse_time_range_text(message.text, on_date=on_date, now_local=now_local)
    if interval is None:
        await message.answer(t("add.time_bad"))
        return
    draft = draft.with_times(interval[0], interval[1])
    await _store(state, draft)
    await _ask_reminder(message, state)


@router.callback_query(AddEvent.time, F.data == callback(CB_ADD, "skip"))
async def step_time_skip(
    query: CallbackQuery, state: FSMContext, user: User, now_utc: datetime
) -> None:
    """«Пропустить»: ставим ближайший круглый час — но не в прошлом."""
    now_local = now_utc.astimezone(tz_for(user.tz))
    draft = await _load(state)
    on_date = draft.day or now_local.date()
    start = (now_local + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    if on_date != start.date():
        start = datetime.combine(on_date, start.timetz())
    draft = draft.with_times(start)
    await _store(state, draft)
    await safe_answer(query)
    await _ask_reminder_callback(query, state)


async def _ask_reminder(message: Message, state: FSMContext) -> None:
    """Шаг «Напомнить?»."""
    await state.set_state(AddEvent.reminder)
    await message.answer(t("add.reminder_prompt"), reply_markup=add_reminder_keyboard())


async def _ask_reminder_callback(query: CallbackQuery, state: FSMContext) -> None:
    """Шаг «Напомнить?» при движении по инлайн-кнопкам."""
    await state.set_state(AddEvent.reminder)
    await show(query, t("add.reminder_prompt"), markup=add_reminder_keyboard())


# ── Шаг 4: напомнить ──────────────────────────────────────────────────────────


@router.callback_query(AddEvent.reminder, F.data.startswith(f"{CB_ADD}:remind:"))
async def step_reminder(
    query: CallbackQuery, state: FSMContext, user: User, now_utc: datetime
) -> None:
    """Выбор смещения напоминания и показ превью."""
    _, _, args = parse_callback(query.data or "")
    raw = args[0] if args else REMINDER_OFF_TOKEN
    offset = REMINDER_OFF if raw == REMINDER_OFF_TOKEN else int(raw)
    draft = (await _load(state)).with_reminder(offset)
    await _store(state, draft)
    now_local = now_utc.astimezone(tz_for(user.tz))
    await state.set_state(AddEvent.confirm)
    await show(query, draft.preview_text(now_local=now_local), markup=add_confirm_keyboard())
    await safe_answer(query)


# ── Шаг 5: превью и подтверждение ─────────────────────────────────────────────


async def _show_preview(
    message: Message, state: FSMContext, draft: DraftState, *, now_local: datetime
) -> None:
    """Показывает превью события (для текстового пути)."""
    await state.set_state(AddEvent.confirm)
    await message.answer(
        draft.preview_text(now_local=now_local), reply_markup=add_confirm_keyboard()
    )


@router.callback_query(AddEvent.confirm, F.data == callback(CB_ADD, "confirm"))
async def confirm_add(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    now_utc: datetime,
    app_settings,
) -> None:
    """Создаёт событие и превращает превью в карточку с действиями."""
    draft = await _load(state)
    start = draft.start_local_any()
    if not draft.title or start is None:
        await toast(query, t("common.not_understood"), alert=True)
        return

    end = draft.end_local_any()
    if end is None:
        end = start + timedelta(minutes=60)

    now_local = now_utc.astimezone(tz_for(user.tz))
    event = await schedule_service.create(
        session,
        user,
        title=draft.title,
        start_local=start,
        end_local=end,
        repeat_rule=draft.repeat_rule,
        category=draft.category,
        reminder_offset=draft.reminder_offset,
        now_utc=now_utc,
        horizon_days=app_settings.reminder_horizon_days,
    )
    await state.clear()

    occurrence = schedule_service.Occurrence(
        event_id=event.id,
        title=event.title,
        category=event.category,
        status=EventStatus(event.status),
        repeat_rule=event.repeat_rule,
        reminder_offset=event.reminder_offset,
        start_local=start,
        end_local=end,
        occurrence_date=start.date(),
    )
    text = t("add.created", title=event.title, when=format_when(start, end, now_local))
    overlap = await _overlap_warning(session, user, occurrence)
    if overlap:
        text = f"{text}\n{overlap}"
    await show(query, text, markup=event_actions_keyboard(occurrence))
    await toast(query, t("common.saved"))


async def _overlap_warning(
    session: AsyncSession, user: User, occurrence: schedule_service.Occurrence
) -> str | None:
    """Предупреждает о наложении с другим событием дня (не блокирует создание)."""
    others = await schedule_service.day_occurrences(session, user, day=occurrence.occurrence_date)
    for other in others:
        if other.event_id == occurrence.event_id:
            continue
        if other.start_local < occurrence.end_local and occurrence.start_local < other.end_local:
            return t(
                "add.overlap",
                title=other.title,
                start=format_time(other.start_local),
                end=format_time(other.end_local),
            )
    return None


@router.callback_query(StateFilter(AddEvent), F.data == callback(CB_ADD, "restart"))
async def restart_add(query: CallbackQuery, state: FSMContext) -> None:
    """«Заново»: чистим черновик и начинаем с названия."""
    await state.set_state(AddEvent.title)
    await state.update_data({DraftState.STATE_KEY: DraftState().to_state()})
    await safe_answer(query)
    await show(
        query,
        f"{t('add.wizard_title')}\n{t('add.wizard_title_hint')}",
        markup=skip_keyboard(CB_ADD),
    )


@router.callback_query(StateFilter(AddEvent), F.data == callback(CB_ADD, "cancel"))
async def cancel_add(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """«Отмена» на любом шаге: возвращаемся в главное меню."""
    from chronos.bot.handlers.menu import render_menu_message

    await state.clear()
    await query.answer(t("common.canceled"))
    await _safe_delete(query.message)
    await render_menu_message(
        query.bot, session=session, user=user, now_utc=now_utc, chat_id=user.telegram_id
    )


@router.callback_query(StateFilter(AddEvent), F.data == callback(CB_ADD, "skip"))
async def skip_add(query: CallbackQuery, state: FSMContext) -> None:
    """«Пропустить» на шаге названия: без названия событие не создаём."""
    await query.answer(t("add.wizard_title_hint"), show_alert=True)


async def _safe_delete(message: Message | None) -> None:
    """Удаляет сообщение, если оно доступно."""
    if message is None:
        return
    try:
        await message.delete()
    except Exception:  # pragma: no cover - сообщение могло быть уже удалено
        logger.debug("Не удалось удалить сообщение мастера")


# ── Работа с FSM-данными ──────────────────────────────────────────────────────


async def _load(state: FSMContext) -> DraftState:
    """Читает черновик из FSM-данных."""
    data = await state.get_data()
    return DraftState.from_state(data.get(DraftState.STATE_KEY))


async def _store(state: FSMContext, draft: DraftState) -> None:
    """Сохраняет черновик в FSM-данные (только примитивы)."""
    await state.update_data({DraftState.STATE_KEY: draft.to_state()})


__all__ = ["router"]
