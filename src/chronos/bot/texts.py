"""Тексты reply-кнопок как константы.

Кнопки reply-клавиатуры фильтруются по тексту, поэтому тексты нужны и
в клавиатуре, и в фильтрах. Локаль фиксируется на старте процесса,
поэтому константы вычисляются один раз.
"""

from __future__ import annotations

from chronos.i18n import t

MENU_BUTTON = t("common.btn_menu")
TIMER_BUTTON = t("common.btn_timer")

__all__ = ["MENU_BUTTON", "TIMER_BUTTON"]
