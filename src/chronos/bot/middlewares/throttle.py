"""Защита от двойных нажатий.

Все действия идемпотентны на уровне БД, но повторный тап по той же кнопке
не должен дважды рисовать сообщение или создавать событие. Дубликат в окне
``CALLBACK_DEDUP_WINDOW`` молча подтверждаем и пропускаем.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from chronos.constants import CALLBACK_DEDUP_WINDOW


class CallbackDedupMiddleware(BaseMiddleware):
    """Пропускает повторный callback с теми же данными от того же пользователя."""

    def __init__(self, window_seconds: float | None = None) -> None:
        self.window = (
            window_seconds
            if window_seconds is not None
            else CALLBACK_DEDUP_WINDOW.total_seconds()
        )
        self._seen: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery) or event.data is None or event.from_user is None:
            return await handler(event, data)

        key = (event.from_user.id, event.data)
        moment = monotonic()
        previous = self._seen.get(key)
        self._seen[key] = moment
        if previous is not None and moment - previous < self.window:
            await event.answer()
            return None
        if len(self._seen) > 512:  # гигиена памяти: чистим устаревшие записи
            threshold = moment - self.window
            self._seen = {k: v for k, v in self._seen.items() if v >= threshold}
        return await handler(event, data)


__all__ = ["CallbackDedupMiddleware"]
