"""Модель «мягких» настроек: key-value на пользователя.

Здесь живут только те настройки, которые не читаются на горячем пути
планировщика (см. docs/DECISIONS.md D-02). Источник правды по таймзоне,
рабочим часам, тихому часу и режиму трекинга — колонки таблицы ``users``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from chronos.models.base import Base
from chronos.models.types import UTCDateTime, utcnow


class Setting(Base):
    """Пара «ключ → значение» для пользователя."""

    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setting user={self.user_id} {self.key}={self.value!r}>"


__all__ = ["Setting"]
