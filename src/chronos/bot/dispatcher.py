"""Сборка Dispatcher: мидлвари + порядок роутеров.

Порядок роутеров = приоритет. Замыкающий router с «не понял» включается
последним, поэтому он ловит только то, что не подошло сценариям.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import datetime

from aiogram import Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage

from chronos.bot.handlers import (
    add,
    commands,
    errors,
    menu,
    onboarding,
    reminders,
    schedule,
    settings,
)
from chronos.bot.middlewares.context import ContextMiddleware, utcnow
from chronos.bot.middlewares.db import DbSessionMiddleware
from chronos.bot.middlewares.errors import ErrorsMiddleware
from chronos.bot.middlewares.throttle import CallbackDedupMiddleware
from chronos.bot.middlewares.user import UserMiddleware
from chronos.config import Settings
from chronos.logging_setup import logger
from chronos.utils.db import Database

#: Порядок включения роутеров: специфичные сценарии → меню → команды → fallback.
ROUTER_ORDER = (
    onboarding.router,
    add.router,
    schedule.router,
    settings.router,
    menu.router,
    reminders.router,
    commands.router,
    errors.router,
)


def _fresh_router(router: Router) -> Router:
    """Копия модульного роутера, пригодная для нового Dispatcher.

    Роутеры в ``bot.handlers`` создаются один раз на модуль (идиома aiogram), а
    aiogram запрещает подключать один Router к двум Dispatcher. Копия позволяет
    собирать Dispatcher многократно: это нужно тестам и перезапуску в dev-режиме.
    """
    return copy.deepcopy(router)


def build_dispatcher(
    settings: Settings,
    database: Database,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> Dispatcher:
    """Собирает Dispatcher с мидлварями и роутерами.

    Хранилище FSM — память процесса: для single-user MVP достаточно. Для
    мультиюзера достаточно заменить ``MemoryStorage`` на Redis-хранилище.
    ``clock`` позволяет подменить «сейчас» в тестах.
    """
    dispatcher = Dispatcher(storage=MemoryStorage())

    # 1. Внешний слой: ошибки (ловят всё) и контекст (время + настройки).
    dispatcher.update.outer_middleware(ErrorsMiddleware())
    dispatcher.update.outer_middleware(ContextMiddleware(settings, clock=clock))

    # 2. Слой данных и пользователя.
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(DbSessionMiddleware(database))
        observer.middleware(UserMiddleware(settings))

    # 3. Защита от двойных тапов (только callback).
    dispatcher.callback_query.middleware(CallbackDedupMiddleware())

    for router in ROUTER_ORDER:
        dispatcher.include_router(_fresh_router(router))

    logger.debug("Dispatcher собран: роутеров={}", len(ROUTER_ORDER))
    return dispatcher


__all__ = ["ROUTER_ORDER", "build_dispatcher"]
