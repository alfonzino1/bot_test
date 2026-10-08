"""Контекст фоновых задач: то, что нужно джобу кроме времени.

Отдельный объект вместо глобальных переменных — задачи можно запускать
в тестах с подставными ботом и БД.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from chronos.config import Settings
from chronos.utils.db import Database


@dataclass(slots=True)
class JobContext:
    """Ресурсы, доступные задачам планировщика."""

    bot: Bot
    database: Database
    settings: Settings


__all__ = ["JobContext"]
