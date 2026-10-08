"""Мелкие помощники отрисовки: «одно сообщение» вместо спама.

Правило UX: одно действие — одно сообщение. Всё, что можно отредактировать,
редактируем; новое сообщение отправляем только когда редактировать нечего.
"""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def show(
    callback: CallbackQuery,
    text: str,
    *,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Показывает текст, редактируя сообщение с кнопками.

    Если сообщение недоступно (старое, удалённое) — отправляет новое.
    """
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
            if "message to edit not found" not in str(exc) and "message can't be edited" not in str(exc):
                raise
    await callback.bot.send_message(callback.from_user.id, text, reply_markup=markup)


async def toast(callback: CallbackQuery, text: str | None = None, *, alert: bool = False) -> None:
    """Всплывающее уведомление в Telegram (тост)."""
    await callback.answer(text or None, show_alert=alert)


async def safe_answer(callback: CallbackQuery, text: str | None = None) -> None:
    """Подтверждает нажатие, если это ещё не сделано.

    Telegram требует ответить на каждый callback: иначе у пользователя
    «крутится» кнопка. Повторный ответ безопасен — ошибку игнорируем.
    """
    try:
        await callback.answer(text or None)
    except TelegramBadRequest:  # уже отвечали — это нормально
        return


__all__ = ["safe_answer", "show", "toast"]
