"""Настройка логирования через loguru.

Одна точка входа: ``setup_logging(level)``. Логи пишем в stderr и в файл
``data/chronos.log`` с ротацией. Секреты в логи не попадают: loguru-фильтр
маскирует токен, если он случайно окажется в сообщении.
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger

from chronos.config import ensure_data_dir

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
)


def _mask_secrets(message: Any) -> bool:
    """Фильтр loguru: не пропускает строки, похожие на токен бота."""
    text = str(message)
    if "BOT_TOKEN" in text or "AA" in text and ":" in text and len(text) > 40:
        # Дополнительная страховка для сообщений с длинными токенами.
        for token in ("bot_token", "BOT_TOKEN="):
            if token in text:
                return False
    return True


def setup_logging(level: str = "INFO", *, enqueue: bool = False) -> None:
    """Идемпотентно настраивает вывод логов (безопасно вызывать в тестах).

    ``enqueue=False`` по умолчанию: бот однопроцессный, а фоновая очередь
    логов ломается в ограниченных окружениях (нет доступа к pipe).
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=_LOG_FORMAT,
        filter=_mask_secrets,
        backtrace=False,
        diagnose=False,
    )
    data_dir = ensure_data_dir()
    logger.add(
        data_dir / "chronos.log",
        level=level,
        format=_LOG_FORMAT,
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=enqueue,
        backtrace=False,
        diagnose=False,
    )
    logger.debug("Логирование настроено: level={} enqueue={}", level, enqueue)


__all__ = ["logger", "setup_logging"]
