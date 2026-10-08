"""Мидлварь ошибок: лог + вежливое сообщение пользователю.

ТЗ, раздел 6: «Ошибки — в лог + вежливое сообщение пользователю».
Ни одно исключение хендлера не должно «съесть» апдейт молча.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from chronos.i18n import t
from chronos.logging_setup import logger


class ErrorsMiddleware(BaseMiddleware):
    """Ловит исключения хендлеров, пишет в лог и отвечает пользователю."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:  # намеренно ловим всё: бот не должен падать
            logger.exception("Ошибка обработки апдейта: {}", exc)
            await self._notify(event)
            return None

    async def _notify(self, event: TelegramObject) -> None:
        """Сообщает пользователю о сбое, не раскрывая деталей."""
        text = t("common.error")
        message = event.message if isinstance(event, Update) else event
        try:
            if isinstance(message, Message):
                await message.answer(text)
            elif isinstance(message, CallbackQuery):
                await message.answer(text, show_alert=True)
        except Exception:  # pragma: no cover - сеть/сообщение недоступны
            logger.warning("Не удалось сообщить пользователю об ошибке")


__all__ = ["ErrorsMiddleware"]
