"""Замыкающие хендлеры: непонятый текст и неизвестные кнопки.

Эти обработчики регистрируются последними, поэтому срабатывают только если
ни один сценарий не подошёл. Микрокопирайт: «Не разобрал 🤔 Попробуй: завтра 15:00».
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from chronos.i18n import t

router = Router(name="fallback")


@router.message(F.text)
async def unknown_text(message: Message) -> None:
    """Текст, который не подошёл ни одному сценарию."""
    await message.answer(t("common.not_understood"))


@router.callback_query()
async def unknown_callback(query: CallbackQuery) -> None:
    """Устаревшая или чужая кнопка — просто подтверждаем нажатие."""
    await query.answer(t("common.error_generic_cb"))


__all__ = ["router"]
