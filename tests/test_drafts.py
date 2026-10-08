"""Тесты черновика события: сериализация в FSM и превью."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from chronos.services.drafts import DraftState
from chronos.utils.datetime_parser import parse_event_text

MOSCOW = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 5, 12, 10, 30, tzinfo=MOSCOW)


def test_из_парсера_в_черновик() -> None:
    draft = parse_event_text("Встреча завтра 15:00-16:00 #работа", now_local=NOW)
    state = DraftState.from_draft(draft)
    assert state.title == "Встреча"
    assert state.day == date(2026, 5, 13)
    assert state.start_local_any() == datetime(2026, 5, 13, 15, 0, tzinfo=MOSCOW)
    assert state.duration == timedelta(hours=1)
    assert state.is_ready is True


def test_сериализация_в_fsm_и_обратно() -> None:
    state = DraftState(title="Созвон", reminder_offset=None, repeat_rule="weekdays")
    restored = DraftState.from_state(state.to_state())
    assert restored == state


def test_пустые_fsm_данные_дают_пустой_черновик() -> None:
    assert DraftState.from_state(None) == DraftState()
    assert DraftState.from_state({}).title == ""


def test_смена_даты_сохраняет_время() -> None:
    state = DraftState.from_draft(
        parse_event_text("Встреча завтра 15:00-16:00", now_local=NOW)
    )
    moved = state.with_date(date(2026, 5, 20))
    assert moved.start_local_any() == datetime(2026, 5, 20, 15, 0, tzinfo=MOSCOW)
    assert moved.end_local_any() == datetime(2026, 5, 20, 16, 0, tzinfo=MOSCOW)


def test_установка_времени_меняет_дату() -> None:
    state = DraftState(title="Дело")
    updated = state.with_times(datetime(2026, 6, 1, 9, 0, tzinfo=MOSCOW))
    assert updated.day == date(2026, 6, 1)
    assert updated.end_local_any() == datetime(2026, 6, 1, 10, 0, tzinfo=MOSCOW)


def test_напоминание_помечается_указанным() -> None:
    state = DraftState(title="Дело").with_reminder(None)
    assert state.reminder_offset is None
    assert state.reminder_specified is True


def test_превью_содержит_название_время_и_напоминание() -> None:
    state = DraftState.from_draft(
        parse_event_text("Встреча завтра 15:00-16:00 #работа", now_local=NOW)
    )
    text = state.preview_text(now_local=NOW)
    assert "Проверь" in text
    assert "Встреча" in text
    assert "завтра 15:00–16:00" in text
    assert "За 15 мин" in text


def test_превью_без_времени_не_падает() -> None:
    state = DraftState(title="Позвонить")
    text = state.preview_text(now_local=NOW)
    assert state.is_ready is False
    assert "Позвонить" in text


def test_подпись_своей_метки() -> None:
    state = DraftState.from_draft(parse_event_text("Медитация #йога 20:00", now_local=NOW))
    assert state.category_caption() == "✏️ йога"
