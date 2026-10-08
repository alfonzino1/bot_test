"""Расписание: ``/today``, неделя и действия по событиям.

Каждая карточка события несёт свои кнопки (✅ Иду / ⏰ Опоздаю / ❌ Отменяю /
🔄 Перенести) — «напоминание всегда с действием» (ТЗ, раздел 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import show, toast
from chronos.bot.keyboards.inline import (
    back_to_menu_keyboard,
    callback,
    event_actions_keyboard,
    move_cancel_keyboard,
    parse_callback,
)
from chronos.bot.states import MoveEvent
from chronos.constants import (
    CB_EVENT,
    CB_MENU_SCHEDULE,
    EventStatus,
    category_emoji,
)
from chronos.i18n import t
from chronos.models import User
from chronos.repositories import schedule as schedule_repo
from chronos.services import schedule as schedule_service
from chronos.services.schedule import Occurrence
from chronos.utils.datetime_parser import parse_event_text
from chronos.utils.formatting import (
    format_date_short,
    format_repeat,
    format_time,
    format_weekday,
    format_when,
)

router = Router(name="schedule")

#: Сколько карточек показываем в «Сегодня», чтобы не заваливать чат.
MAX_CARDS = 6

_STATUS_TEXT_KEYS = {
    EventStatus.PLANNED: "event.status_planned",
    EventStatus.GOING: "schedule.status_going",
    EventStatus.LATE: "schedule.status_late",
    EventStatus.CANCELED: "schedule.status_canceled",
    EventStatus.MOVED: "schedule.status_moved",
    EventStatus.DONE: "event.status_done",
}


def status_text(status: EventStatus) -> str:
    """Подпись статуса события для карточки."""
    return t(_STATUS_TEXT_KEYS.get(status, "event.status_planned"))


def card_text(occurrence: Occurrence) -> str:
    """Карточка события по макету ТЗ."""
    return t(
        "event.card",
        emoji=category_emoji(occurrence.category),
        title=occurrence.title,
        start=format_time(occurrence.start_local),
        end=format_time(occurrence.end_local),
        date=f"{format_weekday(occurrence.occurrence_date)}, {format_date_short(occurrence.occurrence_date)}",
        status=status_text(occurrence.status),
    )


@router.message(Command("today"))
async def handle_today(
    message: Message, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """``/today`` — расписание на сегодня."""
    await send_today(message, session=session, user=user, now_utc=now_utc)


async def send_today(
    message: Message, *, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Отправляет заголовок дня и карточки событий с действиями."""
    tz = schedule_service.user_zone(user)
    local_now = now_utc.astimezone(tz)
    occurrences = await schedule_service.day_occurrences(session, user, day=local_now.date())
    if not occurrences:
        await message.answer(t("today.empty"))
        return

    await message.answer(
        t("today.title", date=f"{format_weekday(local_now.date())}, {format_date_short(local_now.date())}")
    )
    for occurrence in occurrences[:MAX_CARDS]:
        await message.answer(card_text(occurrence), reply_markup=event_actions_keyboard(occurrence))


@router.callback_query(F.data == CB_MENU_SCHEDULE)
async def handle_week(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Экран «Расписание»: неделя вперёд с повторами."""
    tz = schedule_service.user_zone(user)
    local_now = now_utc.astimezone(tz)
    grouped = await schedule_service.week_occurrences(
        session, user, start_day=local_now.date(), days=7
    )
    lines: list[str] = [t("schedule.title")]
    total = 0
    for day, items in grouped.items():
        if not items:
            continue
        lines.append("")
        lines.append(
            t(
                "schedule.day_header",
                weekday=format_weekday(day),
                date=format_date_short(day),
            )
        )
        for occurrence in items:
            total += 1
            suffix = ""
            if occurrence.is_recurring:
                suffix = f" {format_repeat(occurrence.repeat_rule)}"
            elif occurrence.status is not EventStatus.PLANNED:
                suffix = f" · {status_text(occurrence.status)}"
            lines.append(
                "• "
                + t(
                    "schedule.line",
                    start=format_time(occurrence.start_local),
                    end=format_time(occurrence.end_local),
                    title=occurrence.title,
                )
                + suffix
            )
    if total == 0:
        await query.answer()
        await show(query, t("schedule.empty"), markup=back_to_menu_keyboard())
        return
    lines.append("")
    lines.append(t("schedule.hint"))
    await query.answer()
    await show(query, "\n".join(lines), markup=back_to_menu_keyboard())


@router.callback_query(F.data.startswith(f"{CB_EVENT}:"))
async def handle_event_action(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    now_utc: datetime,
) -> None:
    """Действия по карточке события."""
    _, action, args = parse_callback(query.data or "")
    if not args:
        await toast(query, t("event.not_found"), alert=True)
        return
    event_id = int(args[0])
    date_iso = args[1] if len(args) > 1 else None

    event = await schedule_repo.get(session, user.id, event_id)
    if event is None:
        await toast(query, t("event.not_found"), alert=True)
        return

    occurrence = await _occurrence_for(session, user, event, date_iso, now_utc=now_utc)
    if occurrence is None:
        await toast(query, t("event.not_found"), alert=True)
        return

    if action == "go":
        await schedule_service.set_status(session, user, event, EventStatus.GOING, now_utc=now_utc)
        await _refresh_card(query, session, user, event, date_iso, now_utc=now_utc)
        await toast(query, t("event.going_ok"))
    elif action == "late":
        await schedule_service.set_status(session, user, event, EventStatus.LATE, now_utc=now_utc)
        await _refresh_card(query, session, user, event, date_iso, now_utc=now_utc)
        await toast(
            query,
            t("event.late_ok", time=format_time(occurrence.start_local + timedelta(minutes=15))),
        )
    elif action == "cancel":
        await schedule_service.set_status(
            session, user, event, EventStatus.CANCELED, now_utc=now_utc
        )
        await _refresh_card(query, session, user, event, date_iso, now_utc=now_utc)
        await toast(query, t("event.canceled_ok"))
    elif action == "delete":
        await schedule_service.delete(session, user, event)
        await query.answer(t("event.deleted_ok"))
        await show(query, t("event.deleted_ok"), markup=back_to_menu_keyboard())
    elif action == "move":
        await state.set_state(MoveEvent.waiting_time)
        await state.update_data({"event_id": event_id, "occurrence_date": date_iso})
        await query.answer()
        await show(query, t("event.move_prompt"), markup=move_cancel_keyboard())
    elif action == "timer":
        await query.answer()
        await show(query, t("timer.coming_soon"), markup=back_to_menu_keyboard())
    else:
        await toast(query, t("common.error_generic_cb"), alert=True)


async def _refresh_card(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    event,
    date_iso: str | None,
    *,
    now_utc: datetime,
) -> None:
    """Перерисовывает карточку со свежим статусом (без новых сообщений)."""
    occurrence = await _occurrence_for(session, user, event, date_iso, now_utc=now_utc)
    if occurrence is None:
        return
    await show(query, card_text(occurrence), markup=event_actions_keyboard(occurrence))


async def _occurrence_for(
    session: AsyncSession,
    user: User,
    event,
    date_iso: str | None,
    *,
    now_utc: datetime,
) -> Occurrence | None:
    """Находит вхождение события на нужную дату (или ближайшее)."""
    from datetime import date as date_cls

    tz = schedule_service.user_zone(user)
    local_now = now_utc.astimezone(tz)
    if date_iso:
        try:
            day = date_cls.fromisoformat(date_iso)
        except ValueError:
            day = local_now.date()
    else:
        day = local_now.date()
    for occurrence in await schedule_service.day_occurrences(session, user, day=day):
        if occurrence.event_id == event.id:
            return occurrence
    upcoming = await schedule_service.upcoming(
        session, user, now_utc=now_utc, within=timedelta(days=30)
    )
    return upcoming if upcoming and upcoming.event_id == event.id else None


@router.message(MoveEvent.waiting_time, F.text)
async def handle_move_time(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    now_utc: datetime,
) -> None:
    """Перенос: разбираем «завтра 15:00» и переносим вхождение."""
    data = await state.get_data()
    event_id = int(data.get("event_id") or 0)
    date_iso = data.get("occurrence_date")
    event = await schedule_repo.get(session, user.id, event_id)
    if event is None:
        await state.clear()
        await message.answer(t("event.not_found"))
        return

    tz = schedule_service.user_zone(user)
    local_now = now_utc.astimezone(tz)
    parsed = parse_event_text(message.text, now_local=local_now)
    if parsed.start_local is None:
        await message.answer(t("event.move_prompt"))
        return

    occurrence = await _occurrence_for(session, user, event, date_iso, now_utc=now_utc)
    if occurrence is None:
        await state.clear()
        await message.answer(t("event.not_found"))
        return

    moved = await schedule_service.move_occurrence(
        session,
        user,
        event,
        occurrence,
        new_start_local=parsed.start_local,
        new_end_local=parsed.end_local,
        now_utc=now_utc,
    )
    await state.clear()
    start = moved.start_at.astimezone(tz)
    end = moved.end_at.astimezone(tz)
    await message.answer(
        t("event.moved_ok", when=format_when(start, end, local_now))
    )


@router.callback_query(StateFilter(MoveEvent), F.data == callback(CB_EVENT, "move_cancel"))
async def cancel_move(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """«Отмена» при переносе — возврат в меню."""
    from chronos.bot.handlers.menu import render_menu_message

    await state.clear()
    await query.answer(t("common.canceled"))
    await render_menu_message(
        query.bot, session=session, user=user, now_utc=now_utc, chat_id=user.telegram_id
    )


__all__ = ["card_text", "router", "send_today", "status_text"]
