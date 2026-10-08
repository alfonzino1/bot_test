"""Асинхронный доступ к БД: движок, фабрика сессий, проверка соединения.

Одна точка создания движка на процесс. Абстракция БД обеспечена строкой
подключения: SQLite на старте, PostgreSQL — заменой ``DATABASE_URL``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chronos.config import Settings, ensure_data_dir, get_settings
from chronos.logging_setup import logger


def _sqlite_path(url: str) -> Path | None:
    """Путь к файлу SQLite из строки подключения (None для in-memory и не-SQLite)."""
    if not url.startswith("sqlite"):
        return None
    raw = url.split("///", 1)[-1]
    if not raw or raw.startswith(":memory:"):
        return None
    return Path(raw)


def sync_database_url(url: str) -> str:
    """Синхронная версия URL — нужна Alembic (миграции идут без async)."""
    return (
        url.replace("+aiosqlite", "")
        .replace("+asyncpg", "+psycopg")
        .replace("+aiomysql", "+pymysql")
    )


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Создаёт асинхронный движок с корректными настройками для SQLite."""
    config = settings or get_settings()
    if config.is_sqlite:
        ensure_data_dir()
        path = _sqlite_path(config.database_url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(config.database_url, echo=False, pool_pre_ping=True)
    if config.is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record) -> None:  # pragma: no cover
            """SQLite по умолчанию не проверяет внешние ключи — включаем."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    logger.debug("Движок БД создан: {}", config.database_url.split("://", 1)[0])
    return engine


class Database:
    """Владелец движка и фабрики сессий на время жизни процесса."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine: AsyncEngine = create_engine(self.settings)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Сессия с автоматическим rollback при ошибке и commit при успехе."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """Проверка соединения — используется в ``chronos doctor``."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover - диагностический путь
            logger.error("БД недоступна: {}", exc)
            return False

    async def create_all(self) -> None:
        """Создаёт схему напрямую. Только для тестов и быстрого дева без Alembic."""
        from chronos.models import Base  # локальный импорт: регистрация таблиц

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Удаляет схему. Только для тестов."""
        from chronos.models import Base

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
        logger.debug("Движок БД закрыт")


__all__ = ["Database", "create_engine", "sync_database_url", "_sqlite_path"]
