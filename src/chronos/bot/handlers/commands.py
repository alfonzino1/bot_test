"""Команды: /help, /privacy, /mute, /week, /stop и reply-кнопка таймера.

Команды из раздела 5 ТЗ. Таймер (``/timer``, ``/stop``) подключается на этапе 2,
отчёты (``/week``) — на этапе 3; сейчас бот честно об этом сообщает.
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.bot.keyboards.inline import back_to_menu_keyboard, main_menu_inline
from chronos.bot.texts import TIMER_BUTTON
from chronos.i18n import t
from chronos.models import User
from chronos.services import users as users_service
from chronos.utils.datetime_parser import parse_duration_text
from chronos.utils.formatting import humanize_datetime
from chronos.utils.timezones import tz_for

router = Router(name="commands")

_MUTE_OFF_WORDS = {"off", "выкл", "0", "нет"}


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """``/help`` — краткая справка."""
    await message.answer(f"{t('help.title')}\n\n{t('help.body')}")


@router.message(Command("privacy"))
async def handle_privacy(message: Message) -> None:
    """``/privacy`` — что хранится и зачем."""
    await message.answer(f"{t('privacy.title')}\n\n{t('privacy.body')}")


@router.message(Command("mute"))
async def handle_mute(
    message: Message, command: CommandObject, session: AsyncSession, user: User, now_utc: datetime
) -> None:
    """``/mute 2h`` — тишина на указанное время; ``/mute off`` — снять."""
    raw = (command.args or "").strip().lower()
    if raw in _MUTE_OFF_WORDS:
        await users_service.unmute(session, user)
        await message.answer(t("mute.off"))
        return

    duration = parse_duration_text(raw)
    if duration is None:
        await message.answer(t("mute.usage"))
        return

    until = await users_service.mute_for(session, user, duration, now=now_utc)
    local = until.astimezone(tz_for(user.tz))
    await message.answer(t("mute.ok", until=humanize_datetime(local, now_utc.astimezone(tz_for(user.tz)))))


@router.message(Command("week"))
async def handle_week_report(message: Message) -> None:
    """``/week`` — отчёт за неделю (появится на этапе 3)."""
    await message.answer(t("report.coming_soon"), reply_markup=back_to_menu_keyboard())


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    """``/stop`` — остановка таймера (появится на этапе 2)."""
    await message.answer(t("timer.coming_soon"))


@router.message(Command("timer"))
async def handle_timer(message: Message) -> None:
    """``/timer`` — раздел таймера (появится на этапе 2)."""
    await message.answer(t("timer.coming_soon"), reply_markup=back_to_menu_keyboard())


@router.message(F.text == TIMER_BUTTON)
async def handle_timer_button(message: Message) -> None:
    """Reply-кнопка «⏱ Старт/Стоп»."""
    await message.answer(t("timer.coming_soon"), reply_markup=main_menu_inline())


__all__ = ["router"]
