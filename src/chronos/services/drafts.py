"""Черновик события: то, что собирает мастер добавления между шагами.

Черновик живёт в FSM-данных в виде простых значений (строки/числа), поэтому
он совместим с любым хранилищем состояний, включая Redis (задел под мультиюзера).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

from chronos.constants import (
    DEFAULT_EVENT_MINUTES,
    DEFAULT_REMINDER_OFFSET_MIN,
    RepeatRule,
    category_emoji,
    category_label,
)
from chronos.i18n import t
from chronos.utils.datetime_parser import DraftEvent
from chronos.utils.formatting import format_reminder, format_repeat, format_when


@dataclass(frozen=True, slots=True)
class DraftState:
    """Состояние мастера добавления события."""

    title: str = ""
    date_iso: str | None = None
    start_iso: str | None = None
    end_iso: str | None = None
    repeat_rule: str = RepeatRule.NONE.value
    category: str | None = None
    category_custom_label: str | None = None
    reminder_offset: int | None = DEFAULT_REMINDER_OFFSET_MIN
    reminder_specified: bool = False

    #: Ключ, под которым черновик лежит в FSM-данных.
    STATE_KEY = "draft"

    # ── Преобразования ───────────────────────────────────────────────────────

    @classmethod
    def from_draft(cls, draft: DraftEvent) -> DraftState:
        """Из результата парсера текста."""
        start = draft.start_local
        day = start.date() if start is not None else draft.date_local
        return cls(
            title=draft.title,
            date_iso=day.isoformat() if day is not None else None,
            start_iso=start.isoformat() if start is not None else None,
            end_iso=draft.end_local.isoformat() if draft.end_local else None,
            repeat_rule=draft.repeat_rule,
            category=draft.category,
            category_custom_label=draft.category_custom_label,
            reminder_offset=draft.reminder_offset,
            reminder_specified=draft.reminder_specified,
        )

    def to_state(self) -> dict[str, Any]:
        """Сериализация для FSM-данных (только примитивы)."""
        return {
            "title": self.title,
            "date_iso": self.date_iso,
            "start_iso": self.start_iso,
            "end_iso": self.end_iso,
            "repeat_rule": self.repeat_rule,
            "category": self.category,
            "category_custom_label": self.category_custom_label,
            "reminder_offset": self.reminder_offset,
            "reminder_specified": self.reminder_specified,
        }

    @classmethod
    def from_state(cls, payload: Mapping[str, Any] | None) -> DraftState:
        """Восстановление из FSM-данных (устойчиво к пустому словарю)."""
        if not payload:
            return cls()
        offset = payload.get("reminder_offset", DEFAULT_REMINDER_OFFSET_MIN)
        return cls(
            title=str(payload.get("title") or ""),
            date_iso=payload.get("date_iso"),
            start_iso=payload.get("start_iso"),
            end_iso=payload.get("end_iso"),
            repeat_rule=str(payload.get("repeat_rule") or RepeatRule.NONE.value),
            category=payload.get("category"),
            category_custom_label=payload.get("category_custom_label"),
            reminder_offset=None if offset is None else int(offset),
            reminder_specified=bool(payload.get("reminder_specified")),
        )

    # ── Изменения ────────────────────────────────────────────────────────────

    def with_title(self, title: str) -> DraftState:
        return replace(self, title=title.strip()[:200])

    def with_date(self, day: date) -> DraftState:
        """Ставит дату, сохраняя уже выбранное время."""
        start_iso, end_iso = self.start_iso, self.end_iso
        start = self.start_local_any()
        if start is not None:
            shifted = datetime.combine(day, start.timetz()).replace(tzinfo=start.tzinfo)
            start_iso = shifted.isoformat()
            if self.end_iso:
                duration = self.duration or timedelta(minutes=DEFAULT_EVENT_MINUTES)
                end_iso = (shifted + duration).isoformat()
        return replace(self, date_iso=day.isoformat(), start_iso=start_iso, end_iso=end_iso)

    def with_times(self, start: datetime, end: datetime | None = None) -> DraftState:
        """Ставит время начала (и окончания)."""
        if end is None:
            end = start + (self.duration or timedelta(minutes=DEFAULT_EVENT_MINUTES))
        return replace(
            self,
            date_iso=start.date().isoformat(),
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
        )

    def with_repeat(self, rule: str) -> DraftState:
        return replace(self, repeat_rule=rule)

    def with_reminder(self, offset: int | None) -> DraftState:
        return replace(self, reminder_offset=offset, reminder_specified=True)

    def with_category(self, category: str | None, custom_label: str | None = None) -> DraftState:
        return replace(self, category=category, category_custom_label=custom_label)

    # ── Чтение ───────────────────────────────────────────────────────────────

    def start_local_any(self) -> datetime | None:
        """Время начала из черновика (aware, в той зоне, где его задали)."""
        return datetime.fromisoformat(self.start_iso) if self.start_iso else None

    def end_local_any(self) -> datetime | None:
        """Время окончания из черновика."""
        return datetime.fromisoformat(self.end_iso) if self.end_iso else None

    @property
    def day(self) -> date | None:
        """Выбранная дата."""
        if self.date_iso:
            return date.fromisoformat(self.date_iso)
        start = self.start_local_any()
        return start.date() if start else None

    @property
    def duration(self) -> timedelta | None:
        start, end = self.start_local_any(), self.end_local_any()
        if start is None or end is None:
            return None
        return end - start

    @property
    def is_ready(self) -> bool:
        """Хватает ли данных для создания события."""
        return bool(self.title) and self.start_local_any() is not None

    # ── Представление ────────────────────────────────────────────────────────

    def preview_text(self, *, now_local: datetime) -> str:
        """Превью события: «Проверь 👀 … Ок / Заново»."""
        start = self.start_local_any()
        end = self.end_local_any()
        if start is None:
            when = t("add.preview_no_time")
        else:
            if end is None:
                end = start + timedelta(minutes=DEFAULT_EVENT_MINUTES)
            when = format_when(start.astimezone(now_local.tzinfo), end.astimezone(now_local.tzinfo), now_local)
            repeat = format_repeat(self.repeat_rule)
            if repeat:
                when = f"{when}\n{repeat}"
        emoji = category_emoji(self.category)
        return "\n".join(
            [
                t("add.preview_title"),
                t(
                    "add.preview_line",
                    emoji=emoji,
                    title=self.title or t("add.preview_no_title"),
                    when=when,
                    reminder=format_reminder(self.reminder_offset),
                ),
            ]
        )

    def category_caption(self) -> str | None:
        """Подпись категории для карточек (None, если категория не выбрана)."""
        if self.category is None and self.category_custom_label is None:
            return None
        return category_label(self.category_custom_label or self.category)


__all__ = ["DraftState"]
