"""Мидлварь пользователя: достаёт (или создаёт) User и кладёт в ``data``.

Здесь же — белый список Telegram ID: задел под мультиюзера, включается
переменной ``ALLOWED_TELEGRAM_IDS``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from chronos.config import Settings
from chronos.constants import DEFAULT_LOCALE
from chronos.i18n import t
from chronos.logging_setup import logger
from chronos.services import users as users_service


class UserMiddleware(BaseMiddleware):
    """Инжектит ``user`` и ``user_created`` в контекст обработки."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.allowed_ids = settings.allowed_telegram_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        from_user = data.get("event_from_user")
        if session is None or from_user is None or from_user.is_bot:
            return await handler(event, data)

        if self.allowed_ids and from_user.id not in self.allowed_ids:
            logger.warning("Отклонён доступ: telegram_id={}", from_user.id)
            await self._reject(event)
            return None

        user, created = await users_service.ensure_user(
            session,
            telegram_id=from_user.id,
            name=from_user.full_name,
            default_tz=self.settings.default_timezone,
        )
        data["user"] = user
        data["user_created"] = created
        if DEFAULT_LOCALE:  # локаль пока одна, но точка переключения уже есть
            data["locale"] = DEFAULT_LOCALE
        return await handler(event, data)

    async def _reject(self, event: TelegramObject) -> None:
        """Вежливо сообщает, что бот закрыт для посторонних."""
        text = t("common.not_allowed")
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)


__all__ = ["UserMiddleware"]
