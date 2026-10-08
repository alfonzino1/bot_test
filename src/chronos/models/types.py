"""Кастомные типы SQLAlchemy.

``UTCDateTime`` — единственный разрешённый тип для меток времени:
в БД всегда UTC, на выходе всегда aware-datetime (см. docs/DECISIONS.md D-08).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Хранит момент в UTC, возвращает aware-datetime в UTC.

    Naive-datetime на входе запрещён: это почти всегда забытая конвертация зоны,
    и лучше упасть в тесте, чем записать в БД неверное время.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "Naive datetime запрещён: передавай aware-datetime в UTC "
                f"(получено {value.isoformat()})"
            )
        # SQLite не хранит tzinfo — нормализуем в naive-UTC.
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Ожидался datetime из БД, получено {type(value)!r}")
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    """Текущий момент в UTC (aware). Единая точка «сейчас» для всего кода."""
    return datetime.now(UTC)


__all__ = ["UTCDateTime", "utcnow"]
