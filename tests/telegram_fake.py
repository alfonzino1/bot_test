"""Поддельная сессия Telegram: позволяем прогонять сценарии без сети.

``MockSession`` записывает все вызовы Bot API и возвращает правдоподобные
ответы, поэтому через ``Dispatcher.feed_update`` можно проверить весь путь
«апдейт → сервис → ответ пользователю» без токена и интернета.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser

#: Пользователь Telegram в тестах.
TG_USER = TgUser(id=555000111, is_bot=False, first_name="Тест")


class MockSession(BaseSession):
    """Сессия, которая ничего не отправляет, но всё запоминает."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.sent: list[Message] = []
        self._message_id = 1000

    # ── Интерфейс BaseSession ────────────────────────────────────────────────

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        """Заглушка для скачивания файлов (в сценариях этапа 1 не нужна)."""
        yield b""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        """Записывает метод и возвращает подходящий по типу ответ."""
        self.requests.append(method)
        name = type(method).__name__
        payload = method.model_dump(exclude_none=True)

        if name == "SendMessage":
            message = self._make_message(
                chat_id=int(payload.get("chat_id", 1)), text=str(payload.get("text", ""))
            )
            self.sent.append(message)
            return message
        if name in {"EditMessageText", "EditMessageCaption"}:
            return self._make_message(
                chat_id=int(payload.get("chat_id", 1)),
                text=str(payload.get("text", "")),
                message_id=int(payload.get("message_id", 1)),
            )
        return True

    # ── Помощники ────────────────────────────────────────────────────────────

    def _make_message(self, *, chat_id: int, text: str, message_id: int | None = None) -> Message:
        self._message_id += 1
        return Message(
            message_id=message_id or self._message_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type="private"),
            from_user=None,
            text=text,
        )

    # ── Удобные выборки для проверок ─────────────────────────────────────────

    @property
    def texts(self) -> list[str]:
        """Тексты всех сообщений и правок в порядке вызовов."""
        result: list[str] = []
        for method in self.requests:
            payload = method.model_dump(exclude_none=True)
            text = payload.get("text")
            if isinstance(text, str):
                result.append(text)
        return result

    def last_text(self) -> str:
        """Текст последнего сообщения/правки."""
        texts = self.texts
        assert texts, "Бот ничего не отправил"
        return texts[-1]

    def last_markup(self) -> Any:
        """Разметка последнего вызова с клавиатурой."""
        for method in reversed(self.requests):
            payload = method.model_dump(exclude_none=False)
            markup = payload.get("reply_markup")
            if markup is not None:
                return markup
        return None

    def last_message(self) -> Message:
        """Последнее отправленное сообщение (для callback'ов)."""
        assert self.sent, "Бот ничего не отправил"
        return self.sent[-1]

    def has_reply_keyboard(self) -> bool:
        """Была ли в ответах reply-клавиатура (а не inline)."""
        for method in self.requests:
            markup = method.model_dump(exclude_none=True).get("reply_markup")
            if isinstance(markup, dict) and "keyboard" in markup:
                return True
        return False


def build_bot(session: MockSession) -> Bot:
    """Bot с поддельной сессией (токен валиден по формату, сеть не нужна)."""
    return Bot(token="123456:TEST-TOKEN", session=session)


def user_message(text: str, *, message_id: int = 1, chat_id: int = TG_USER.id) -> Message:
    """Текстовое сообщение от пользователя."""
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="private"),
        from_user=TG_USER,
        text=text,
    )


def button_press(data: str, *, message: Message) -> CallbackQuery:
    """Нажатие inline-кнопки в конкретном сообщении бота."""
    return CallbackQuery(
        id=f"cb-{data}",
        from_user=TG_USER,
        chat_instance="test",
        data=data,
        message=message,
    )


__all__ = [
    "MockSession",
    "TG_USER",
    "build_bot",
    "button_press",
    "user_message",
]
