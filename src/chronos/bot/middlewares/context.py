"""Мидлварь контекста: текущее время и настройки процесса в ``data``.

Хендлеры не вызывают ``datetime.now()`` и не читают env напрямую — всё приходит
из контекста, поэтому тесты могут подменить время.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from chronos.config import Settings


def utcnow() -> datetime:
    """Текущий момент UTC (отдельная функция — удобно подменять в тестах)."""
    return datetime.now(UTC)


class ContextMiddleware(BaseMiddleware):
    """Добавляет в ``data``: ``now_utc`` и ``app_settings``."""

    def __init__(self, settings: Settings, *, clock: Callable[[], datetime] = utcnow) -> None:
        self.settings = settings
        self.clock = clock

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["now_utc"] = self.clock()
        data["app_settings"] = self.settings
        return await handler(event, data)


__all__ = ["ContextMiddleware", "utcnow"]
