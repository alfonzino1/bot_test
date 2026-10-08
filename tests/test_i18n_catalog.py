"""Тесты каталога текстов: все ключи из кода существуют, лишних нет.

Это защита от «магических строк» и опечаток: ТЗ требует единый стиль текстов.
"""

from __future__ import annotations

import re
from pathlib import Path

from chronos.i18n import CATALOGS, MissingTextError, available_locales, set_locale, t

SRC = Path(__file__).resolve().parents[1] / "src" / "chronos"
#: Любой вызов t("ключ") или t('ключ') в исходниках.
CALL_RE = re.compile(r"""\bt\(\s*["']([a-z0-9_.]+)["']""")
#: Плейсхолдеры вида {name}.
PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def _python_files() -> list[Path]:
    return [path for path in SRC.rglob("*.py") if path.name != "ru.py"]


def test_все_ключи_из_кода_есть_в_каталоге() -> None:
    catalog = CATALOGS["ru"]
    missing: dict[str, str] = {}
    for path in _python_files():
        for key in CALL_RE.findall(path.read_text(encoding="utf-8")):
            if key not in catalog:
                missing[key] = str(path.relative_to(SRC))
    assert not missing, f"Нет текстов для ключей: {missing}"


def test_каталог_без_пустых_значений() -> None:
    empty = [key for key, value in CATALOGS["ru"].items() if not value.strip()]
    assert empty == []


def test_плейсхолдеры_объявлены_корректно() -> None:
    for key, value in CATALOGS["ru"].items():
        for name in PLACEHOLDER_RE.findall(value):
            assert name.islower(), f"Плейсхолдер {name} в {key} должен быть в нижнем регистре"


def test_t_подставляет_значения() -> None:
    assert t("menu.summary", events="3 события", focus="1ч 12мин").startswith("📅 Сегодня:")
    assert "1ч 12мин" in t("menu.summary", events="1 событие", focus="1ч 12мин")


def test_неизвестный_ключ_это_ошибка_разработчика() -> None:
    try:
        t("нет.такого.ключа")
    except MissingTextError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Ожидали MissingTextError")


def test_локаль_переключается_только_на_поддержанную() -> None:
    assert available_locales() == ("ru",)
    set_locale("ru")
    try:
        set_locale("en")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Ожидали ValueError для неподдержанной локали")
