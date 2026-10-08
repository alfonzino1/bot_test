"""Мини-i18n: единственная точка получения текстов интерфейса.

Задел на мультиязычность: каталоги лежат в отдельных модулях, активная локаль
выбирается ``set_locale()``. Пока поддерживается только ``ru``.
"""

from __future__ import annotations

from chronos.constants import DEFAULT_LOCALE, SUPPORTED_LOCALES
from chronos.i18n import ru

CATALOGS: dict[str, dict[str, str]] = {ru_key: ru.CATALOG for ru_key in ("ru",)}

_active_locale = DEFAULT_LOCALE


class MissingTextError(KeyError):
    """Обращение к несуществующему ключу текста — это баг, а не рантайм-ситуация."""


def available_locales() -> tuple[str, ...]:
    return SUPPORTED_LOCALES


def current_locale() -> str:
    return _active_locale


def set_locale(locale: str) -> None:
    """Переключает активную локаль (для тестов и будущего мультиязычного UI)."""
    global _active_locale
    if locale not in CATALOGS:
        raise ValueError(f"Локаль не поддержана: {locale!r}")
    _active_locale = locale


def t(key: str, **kwargs: object) -> str:
    """Возвращает текст по ключу, подставляя плейсхолдеры ``str.format``."""
    catalog = CATALOGS[_active_locale]
    try:
        template = catalog[key]
    except KeyError as exc:  # pragma: no cover - защита от опечаток в ключах
        raise MissingTextError(f"Нет текста для ключа {key!r} ({_active_locale})") from exc
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError) as exc:  # pragma: no cover
        raise MissingTextError(f"Плейсхолдеры не совпали для {key!r}: {exc}") from exc


__all__ = [
    "CATALOGS",
    "MissingTextError",
    "available_locales",
    "current_locale",
    "set_locale",
    "t",
]
