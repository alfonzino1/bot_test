"""Задача «напоминания»: раз в минуту проверяет pending и отправляет.

Идемпотентность: напоминание помечается отправленным только после успешной
отправки, а уникальный ключ БД не даёт создать дубль (docs/DECISIONS.md D-07).
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from chronos.bot.keyboards.inline import reminder_keyboard
from chronos.jobs.context import JobContext
from chronos.logging_setup import logger
from chronos.repositories import reminders as reminders_repo
from chronos.services import reminders as reminders_service


async def reminder_tick(ctx: JobContext, *, now_utc: datetime | None = None) -> int:
    """Отправляет все созревшие напоминания. Возвращает количество отправленных."""
    moment = now_utc or datetime.now(UTC)
    sent = 0
    async with ctx.database.session() as session:
        items = await reminders_service.collect_due(session, now_utc=moment)
        for item in items:
            try:
                message = await ctx.bot.send_message(
                    chat_id=item.user.telegram_id,
                    text=item.text,
                    reply_markup=reminder_keyboard(item.reminder.id, item.event.id),
                )
            except TelegramForbiddenError:
                # Пользователь заблокировал бота: напоминание больше не нужно.
                logger.warning("Бот заблокирован пользователем id={}", item.user.id)
                await reminders_repo.mark_canceled(session, item.reminder)
                continue
            except TelegramRetryAfter as exc:  # pragma: no cover - защита от лимитов
                logger.warning("Лимит Telegram: повтор через {} c", exc.retry_after)
                continue
            except Exception as exc:  # pragma: no cover - сеть/прочее
                logger.error("Не удалось отправить напоминание id={}: {}", item.reminder.id, exc)
                continue

            await reminders_repo.mark_sent(session, item.reminder, sent_at=moment)
            logger.info(
                "Напоминание отправлено: id={} chat={} message_id={}",
                item.reminder.id,
                item.user.telegram_id,
                message.message_id,
            )
            sent += 1
    if sent:
        logger.debug("Напоминаний отправлено: {}", sent)
    return sent


__all__ = ["reminder_tick"]
