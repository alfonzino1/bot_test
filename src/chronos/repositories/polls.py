"""Репозиторий опросов о времени (пассивные и контекстные)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import PollKind, PollStatus
from chronos.models import Poll


async def ensure_pending(
    session: AsyncSession,
    *,
    user_id: int,
    kind: PollKind,
    slot_at: datetime,
    schedule_id: int | None = None,
) -> Poll:
    """Идемпотентно создаёт опрос на часовой слот (уникальный ключ БД)."""
    existing = await session.execute(
        select(Poll).where(
            Poll.user_id == user_id, Poll.kind == kind, Poll.slot_at == slot_at
        )
    )
    poll = existing.scalar_one_or_none()
    if poll is not None:
        return poll
    poll = Poll(
        user_id=user_id,
        kind=kind,
        slot_at=slot_at,
        schedule_id=schedule_id,
        status=PollStatus.PENDING,
    )
    session.add(poll)
    await session.flush()
    return poll


async def get(session: AsyncSession, poll_id: int) -> Poll | None:
    """Опрос по ID (из callback-данных)."""
    return await session.get(Poll, poll_id)


async def pending_for_user(
    session: AsyncSession, user_id: int, *, kind: PollKind | None = None
) -> Sequence[Poll]:
    """Неотвеченные опросы пользователя (последний — первым)."""
    statement = select(Poll).where(
        Poll.user_id == user_id, Poll.status == PollStatus.PENDING
    )
    if kind is not None:
        statement = statement.where(Poll.kind == kind)
    result = await session.execute(statement.order_by(Poll.sent_at.desc()))
    return result.scalars().all()


async def last_pending(session: AsyncSession, user_id: int, *, kind: PollKind) -> Poll | None:
    """Последний неотвеченный опрос указанного вида."""
    polls = await pending_for_user(session, user_id, kind=kind)
    return polls[0] if polls else None


async def mark_answered(
    session: AsyncSession, poll: Poll, *, answer: str, answered_at: datetime
) -> Poll:
    """Фиксирует ответ пользователя."""
    poll.answer = answer
    poll.answered_at = answered_at
    poll.status = PollStatus.ANSWERED
    await session.flush()
    return poll


async def mark_skipped(session: AsyncSession, poll: Poll) -> Poll:
    """Пользователь нажал «Пропустить» — больше не спрашиваем."""
    poll.status = PollStatus.SKIPPED
    await session.flush()
    return poll


async def set_message_id(session: AsyncSession, poll: Poll, message_id: int | None) -> Poll:
    """Запоминает id сообщения опроса (одно редактируемое сообщение)."""
    poll.message_id = message_id
    await session.flush()
    return poll


async def last_answered(session: AsyncSession, user_id: int) -> Poll | None:
    """Последний отвеченный опрос — источник подписи «то же, что час назад»."""
    result = await session.execute(
        select(Poll)
        .where(Poll.user_id == user_id, Poll.status == PollStatus.ANSWERED)
        .order_by(Poll.answered_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def expire_stale(session: AsyncSession, before: datetime) -> int:
    """Помечает протухшие опросы истёкшими (ответ по старым кнопкам не нужен)."""
    result = await session.execute(
        select(Poll).where(Poll.status == PollStatus.PENDING, Poll.sent_at < before)
    )
    polls = list(result.scalars().all())
    for poll in polls:
        poll.status = PollStatus.EXPIRED
    await session.flush()
    return len(polls)


__all__ = [
    "ensure_pending",
    "expire_stale",
    "get",
    "last_answered",
    "last_pending",
    "mark_answered",
    "mark_skipped",
    "pending_for_user",
    "set_message_id",
]
