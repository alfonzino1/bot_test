"""Репозиторий «мягких» настроек (key-value на пользователя)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos.constants import SettingKey
from chronos.models import Setting


async def get_value(session: AsyncSession, user_id: int, key: SettingKey | str) -> str | None:
    """Значение настройки или None."""
    result = await session.execute(
        select(Setting.value).where(Setting.user_id == user_id, Setting.key == str(key))
    )
    return result.scalar_one_or_none()


async def set_value(
    session: AsyncSession, user_id: int, key: SettingKey | str, value: str
) -> Setting:
    """Идемпотентный upsert настройки (single-user MVP: селект + вставка/апдейт)."""
    key_str = str(key)
    existing = await session.execute(
        select(Setting).where(Setting.user_id == user_id, Setting.key == key_str)
    )
    setting = existing.scalar_one_or_none()
    if setting is None:
        setting = Setting(user_id=user_id, key=key_str, value=value)
        session.add(setting)
    else:
        setting.value = value
    await session.flush()
    return setting


async def get_all(session: AsyncSession, user_id: int) -> dict[str, str]:
    """Все настройки пользователя одним словарём (для проверок тишины)."""
    result = await session.execute(select(Setting).where(Setting.user_id == user_id))
    return {row.key: row.value for row in result.scalars().all()}


async def delete_key(session: AsyncSession, user_id: int, key: SettingKey | str) -> None:
    """Удаляет настройку (например, истёкшую тишину)."""
    await session.execute(
        delete(Setting).where(Setting.user_id == user_id, Setting.key == str(key))
    )
    await session.flush()


__all__ = ["delete_key", "get_all", "get_value", "set_value"]
