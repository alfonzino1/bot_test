"""Reply-клавиатура: два постоянных действия.

Кнопки дублируют команды и всегда под рукой — это «правило одного тапа»
для двух самых частых действий: вернуться в меню и запустить/остановить таймер.
"""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from chronos.i18n import t


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура: «🏠 Меню» и «⏱ Старт/Стоп»."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("common.btn_menu")),
                KeyboardButton(text=t("common.btn_timer")),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t("common.btn_menu"),
    )


__all__ = ["main_menu_keyboard"]
