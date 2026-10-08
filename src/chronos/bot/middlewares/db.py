"""Мидлварь сессии БД: одна сессия на обработку одного апдейта.

Границы транзакции — здесь: успешный хендлер коммитит, исключение откатывает
(docs/DECISIONS.md, принципы слоя данных).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from chronos.utils.db import Database


class DbSessionMiddleware(BaseMiddleware):
    """Открывает ``AsyncSession`` и кладёт её в ``data['session']``."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.database.session() as session:
            data["session"] = session
            return await handler(event, data)


__all__ = ["DbSessionMiddleware"]
