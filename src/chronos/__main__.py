"""Точка входа: ``python -m chronos`` запускает бота, ``doctor`` — самопроверку.

Запуск:

* ``python -m chronos``         — бот в режиме long polling;
* ``python -m chronos doctor``  — проверка конфигурации, БД, текстов и задач.

Миграции применяются отдельно: ``alembic upgrade head`` (Alembic с самого начала,
ТЗ раздел 6).
"""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import inspect

from chronos.bot.dispatcher import ROUTER_ORDER, build_dispatcher
from chronos.config import get_settings
from chronos.i18n import CATALOGS, current_locale, t
from chronos.jobs.context import JobContext
from chronos.jobs.scheduler import build_scheduler
from chronos.logging_setup import logger, setup_logging
from chronos.utils.db import Database
from chronos.utils.timezones import tz_for


async def run_bot() -> int:
    """Запускает polling и планировщик до остановки процесса."""
    settings = get_settings()
    setup_logging(settings.log_level, enqueue=settings.log_enqueue)

    if not settings.has_bot_token:
        logger.error("BOT_TOKEN не задан: заполни .env (см. .env.example)")
        return 2

    database = Database(settings)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=None),
    )
    dispatcher = build_dispatcher(settings, database)
    ctx = JobContext(bot=bot, database=database, settings=settings)
    scheduler = build_scheduler(ctx)
    scheduler.start()

    logger.info("Хронос запущен: локаль={} задач={}", current_locale(), len(scheduler.get_jobs()))
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await database.dispose()
        logger.info("Хронос остановлен")
    return 0


async def doctor() -> int:
    """Самопроверка окружения: конфиг, БД, тексты, планировщик."""
    settings = get_settings()
    setup_logging("INFO", enqueue=settings.log_enqueue)
    problems: list[str] = []

    print(f"Хронос {await _version()} — самопроверка")
    print(f"  • таймзона по умолчанию: {settings.default_timezone}")
    print(f"  • база: {settings.database_url.split('://', 1)[0]}")
    print(f"  • белый список: {'включён' if settings.allowed_telegram_ids else 'выключен'}")

    if settings.has_bot_token:
        print("  • BOT_TOKEN: задан ✅")
    else:
        problems.append("BOT_TOKEN не задан — бот не сможет запуститься (это ожидаемо до .env)")
        print("  • BOT_TOKEN: не задан ⚠️")

    zone = tz_for(settings.default_timezone)
    print(f"  • зона разобрана: {zone}")

    # Тексты: каталог должен быть полным и не пустым.
    empty = [key for key, value in CATALOGS["ru"].items() if not value.strip()]
    if empty:
        problems.append(f"пустые тексты: {empty[:5]}")
    print(f"  • текстов в каталоге: {len(CATALOGS['ru'])}")
    print(f"  • пример текста: {t('common.saved')}")

    database = Database(settings)
    try:
        if await database.ping():
            print("  • подключение к БД: ок ✅")
            tables = await _tables(database)
            if tables:
                print(f"  • таблиц в схеме: {len(tables)} ({', '.join(sorted(tables))})")
            else:
                problems.append("схема пуста: примени миграции — alembic upgrade head")
                print("  • схема: пусто ⚠️")
        else:
            problems.append("БД недоступна")
            print("  • подключение к БД: ошибка ❌")
    finally:
        await database.dispose()

    print(f"  • роутеров: {len(ROUTER_ORDER)}")
    print(f"  • задач планировщика: 1 (напоминания)")

    if problems:
        print("\nЕсть что поправить:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nВсё готово ✅ Запуск: python -m chronos")
    return 0


async def _tables(database: Database) -> list[str]:
    """Список таблиц в текущей схеме БД."""
    async with database.engine.connect() as connection:
        names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    return list(names)


async def _version() -> str:
    """Версия приложения из пакета."""
    from chronos import __version__

    return __version__


def main(argv: list[str] | None = None) -> int:
    """CLI: ``run`` (по умолчанию) или ``doctor``."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "run"
    if command in {"doctor", "check"}:
        return asyncio.run(doctor())
    if command in {"run", "start"}:
        try:
            return asyncio.run(run_bot())
        except KeyboardInterrupt:  # pragma: no cover - ручная остановка
            print("\nОстановлено пользователем")
            return 0
    print(__doc__)
    print(f"Неизвестная команда: {command!r}. Доступно: run, doctor")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["doctor", "main", "run_bot"]
