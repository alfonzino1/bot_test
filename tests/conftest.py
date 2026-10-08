"""Общие фикстуры тестов.

Внешние сервисы не нужны: БД — SQLite в tmp, «сейчас» — фиксированный момент,
Telegram — поддельная сессия (см. ``tests/telegram_fake.py``).
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from chronos.config import Settings
from chronos.constants import TrackingMode
from chronos.models import User
from chronos.utils.db import Database

#: «Сейчас» в тестах: вторник, 12 мая 2026, 10:30 по Москве (07:30 UTC).
NOW_UTC = datetime(2026, 5, 12, 7, 30, tzinfo=UTC)
MOSCOW = ZoneInfo("Europe/Moscow")
TELEGRAM_ID = 555000111


@pytest.fixture
def clock() -> datetime:
    """Фиксированное «сейчас» для детерминированных проверок."""
    return NOW_UTC


@pytest.fixture
def data_dir() -> Iterator[Path]:
    """Каталог для файловой SQLite внутри проекта.

    Специально не ``tmp_path``: тесты должны работать и в ограниченных
    окружениях, где системный временный каталог недоступен.
    """
    base = Path(__file__).resolve().parents[1] / ".pytest-data"
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Настройки с файловой SQLite (in-memory не годится для пула соединений)."""
    return Settings(
        _env_file=None,
        BOT_TOKEN="123456:TEST-TOKEN",
        DATABASE_URL=f"sqlite+aiosqlite:///{(data_dir / 'test.db').as_posix()}",
        DEFAULT_TIMEZONE="Europe/Moscow",
    )


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    """Пустая схема, созданная из моделей (миграции проверяются отдельно)."""
    db = Database(settings)
    await db.create_all()
    try:
        yield db
    finally:
        await db.dispose()


@pytest_asyncio.fixture
async def user(database: Database) -> User:
    """Пользователь, прошедший онбординг, с московской зоной."""
    async with database.session() as session:
        user = User(
            telegram_id=TELEGRAM_ID,
            name="Тест",
            tz="Europe/Moscow",
            tracking_mode=TrackingMode.BOTH,
            onboarded_at=NOW_UTC,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user
