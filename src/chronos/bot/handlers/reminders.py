"""Кнопки под напоминанием: «Да, старт» / «Нет» / «Позже».

Напоминание всегда приходит с действием (ТЗ, раздел 3, правило контекста).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import toast
from chronos.bot.keyboards.inline import parse_callback
from chronos.i18n import t
from chronos.models import User
from chronos.repositories import reminders as reminders_repo
from chronos.services import reminders as reminders_service

router = Router(name="reminder_buttons")

#: На сколько откладываем по кнопке «Позже».
SNOOZE_DELAY = timedelta(minutes=10)


@router.callback_query(F.data.startswith("rem:"))
async def handle_reminder_button(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """Обрабатывает нажатия на кнопки напоминания."""
    _, action, args = parse_callback(query.data or "")
    if not args:
        await toast(query, t("common.error_generic_cb"), alert=True)
        return
    reminder_id = int(args[0])
    reminder = await reminders_repo.get_by_id(session, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        await toast(query, t("common.error_generic_cb"), alert=True)
        return

    if action == "start":
        # Этап 2 заменит эту заглушку на реальный запуск таймера.
        await query.answer()
        if query.message is not None:
            await query.message.answer(t("timer.coming_soon"))
    elif action == "no":
        await _drop_keyboard(query)
        await toast(query, t("reminder.no_ok"))
    elif action == "later":
        await reminders_service.reschedule_later(
            session, reminder, at=now_utc + SNOOZE_DELAY
        )
        await _drop_keyboard(query)
        await toast(query, t("reminder.later_ok"))
    else:
        await toast(query, t("common.error_generic_cb"), alert=True)


async def _drop_keyboard(query: CallbackQuery) -> None:
    """Убирает кнопки у отправленного напоминания."""
    try:
        if query.message is not None:
            await query.message.edit_reply_markup(reply_markup=None)
    except Exception:  # pragma: no cover - сообщение могло быть удалено
        return


__all__ = ["SNOOZE_DELAY", "router"]
