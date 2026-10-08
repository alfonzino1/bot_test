"""Главное меню: сводка дня + кнопки действий.

Меню доступно тремя путями: ``/menu``, reply-кнопка «🏠 Меню» и inline-кнопка
«Назад». Во всех случаях это одно и то же редактируемое сообщение.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.handlers.ui import show
from chronos.bot.keyboards.inline import (
    back_to_menu_keyboard,
    main_menu_inline,
)
from chronos.bot.texts import MENU_BUTTON
from chronos.constants import CB_MENU_MAIN, CB_MENU_REPORT, CB_MENU_TIMER
from chronos.i18n import t
from chronos.models import User
from chronos.services import menu as menu_service

router = Router(name="menu")


async def render_menu_message(
    target: Message | Bot,
    *,
    session: AsyncSession,
    user: User,
    now_utc,
    chat_id: int | None = None,
) -> None:
    """Отправляет меню новым сообщением (``/menu``, «🏠 Меню», финал онбординга)."""
    summary = await menu_service.today_summary(session, user, now_utc=now_utc)
    text = menu_service.build_menu_text(user, summary)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu_inline())
        return
    if chat_id is None:
        raise ValueError("Для отправки через Bot нужен chat_id")
    await target.send_message(chat_id, text, reply_markup=main_menu_inline())


@router.message(Command("menu"))
async def handle_menu_command(
    message: Message, session: AsyncSession, user: User, now_utc
) -> None:
    """``/menu`` — главное меню."""
    await render_menu_message(message, session=session, user=user, now_utc=now_utc)


@router.message(F.text == MENU_BUTTON)
async def handle_menu_button(
    message: Message, session: AsyncSession, user: User, now_utc
) -> None:
    """Reply-кнопка «🏠 Меню»."""
    await render_menu_message(message, session=session, user=user, now_utc=now_utc)


@router.callback_query(F.data == CB_MENU_MAIN)
async def handle_menu_callback(
    query: CallbackQuery, session: AsyncSession, user: User, now_utc
) -> None:
    """Кнопка «Назад» в меню."""
    summary = await menu_service.today_summary(session, user, now_utc=now_utc)
    await query.answer()
    await show(
        query,
        menu_service.build_menu_text(user, summary),
        markup=main_menu_inline(),
    )


@router.callback_query(F.data == CB_MENU_TIMER)
async def handle_timer_stub(query: CallbackQuery) -> None:
    """Раздел «Таймер» появится на этапе 2 — честно сообщаем об этом."""
    await query.answer()
    await show(query, t("timer.coming_soon"), markup=back_to_menu_keyboard())


@router.callback_query(F.data == CB_MENU_REPORT)
async def handle_report_stub(query: CallbackQuery) -> None:
    """Раздел «Отчёт» появится на этапе 3."""
    await query.answer()
    await show(query, t("report.coming_soon"), markup=back_to_menu_keyboard())


__all__ = ["render_menu_message", "router"]
