"""Сквозные тесты сценариев: апдейт → сервис → ответ бота.

Telegram не нужен: используется ``MockSession`` (см. ``tests/telegram_fake.py``).
Здесь проверяются именно сценарии ТЗ: онбординг, меню, добавление, /today,
настройки, тишина и фоновая отправка напоминаний.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import Update

from chronos.bot.dispatcher import build_dispatcher
from chronos.constants import SettingKey
from chronos.jobs.context import JobContext
from chronos.jobs.reminders import reminder_tick
from chronos.repositories import reminders as reminders_repo
from chronos.repositories import schedule as schedule_repo
from chronos.repositories import settings as settings_repo
from chronos.repositories import users as users_repo
from chronos.services import schedule as schedule_service
from chronos.services import users as users_service
from tests.telegram_fake import (
    MockSession,
    TG_USER,
    build_bot,
    button_press,
    user_message,
)

MOSCOW = ZoneInfo("Europe/Moscow")
NOW_UTC = datetime(2026, 5, 12, 7, 30, tzinfo=UTC)  # 10:30 МСК, вторник


class Flow:
    """Мини-раннер сценария: отправка сообщений и нажатий с автонумерацией."""

    def __init__(self, dispatcher, bot, mock: MockSession) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.mock = mock
        self._update_id = 0

    def _next_id(self) -> int:
        self._update_id += 1
        return self._update_id

    async def send(self, text: str) -> None:
        """Отправляет текстовое сообщение пользователя."""
        await self.dispatcher.feed_update(
            self.bot,
            Update(
                update_id=self._next_id(),
                message=user_message(text, message_id=self._update_id),
            ),
        )

    async def press(self, data: str) -> None:
        """Нажимает inline-кнопку в последнем сообщении бота."""
        await self.dispatcher.feed_update(
            self.bot,
            Update(
                update_id=self._next_id(),
                callback_query=button_press(data, message=self.mock.last_message()),
            ),
        )

    async def onboard(self) -> None:
        """Проходит онбординг как обычный пользователь."""
        await self.send("/start")
        await self.press("onb:tz:0")
        await self.press("onb:mode:both")
        await self.press("onb:work:10-19")


def build_flow(database, settings, clock) -> tuple[Flow, MockSession]:
    """Собирает Dispatcher с поддельным Telegram и возвращает раннер."""
    mock = MockSession()
    bot = build_bot(mock)
    dispatcher = build_dispatcher(settings, database, clock=lambda: clock)
    return Flow(dispatcher, bot, mock), mock


async def test_онбординг_доводит_до_меню(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)

    await flow.send("/start")
    assert "Шаг 1" in mock.last_text()
    assert "Где ты по времени" in mock.last_text()

    await flow.press("onb:tz:0")
    assert "Шаг 2" in mock.last_text()

    await flow.press("onb:mode:both")
    assert "Шаг 3" in mock.last_text()

    await flow.press("onb:work:10-19")

    texts = mock.texts
    assert any("Готово" in text for text in texts)
    assert any("картина дня" in text for text in texts)
    assert mock.has_reply_keyboard(), "reply-клавиатура появляется после онбординга"

    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
    assert stored is not None
    assert stored.is_onboarded is True
    assert stored.tz == "Europe/Moscow"
    assert stored.work_start.hour == 10 and stored.work_end.hour == 19


async def test_повторный_start_ведёт_в_меню(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    await flow.send("/start")
    assert "картина дня" in mock.last_text()
    assert "Шаг 1" not in mock.last_text()


async def test_главное_меню_и_кнопки_заглушек(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    await flow.send("/menu")
    assert "Сегодня" in mock.last_text()
    assert "0 событий" in mock.last_text()

    await flow.press("menu:timer")
    assert "Таймер подключу" in mock.last_text()

    await flow.press("menu:schedule")
    assert "Пока пусто" in mock.last_text()


async def test_быстрое_добавление_и_подтверждение(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    await flow.send("/add Встреча сегодня 15:00-16:00 #работа")
    preview = mock.last_text()
    assert "Проверь" in preview
    assert "Встреча" in preview
    assert "15:00–16:00" in preview

    await flow.press("add:confirm")
    assert "Записал" in mock.last_text()

    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        events = await schedule_repo.list_for_window(
            session, stored.id, NOW_UTC - timedelta(hours=1), NOW_UTC + timedelta(days=2)
        )
        assert len(events) == 1
        event = events[0]
        assert event.title == "Встреча"
        assert event.category == "work"
        assert event.reminder_offset == 15
        reminders = await reminders_repo.list_for_event(session, event.id)
    assert len(reminders) == 1
    assert reminders[0].status.value == "pending"

    await flow.send("/today")
    assert "Встреча" in mock.last_text()
    markup = mock.last_markup()
    callbacks = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
    assert any(data.startswith("ev:go:") for data in callbacks)
    assert any(data.startswith("ev:cancel:") for data in callbacks)


async def test_мастер_добавления_спрашивает_недостающее(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    # В строке нет времени — бот не падает, а спрашивает его.
    await flow.send("/add Позвонить маме завтра")
    assert "Во сколько" in mock.last_text()

    await flow.send("16:00")
    assert "Напомнить" in mock.last_text()

    await flow.press("add:remind:60")
    assert "Проверь" in mock.last_text()
    assert "За 1 ч" in mock.last_text()

    await flow.press("add:confirm")
    assert "Записал" in mock.last_text()

    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        events = await schedule_repo.list_for_window(
            session, stored.id, NOW_UTC, NOW_UTC + timedelta(days=3)
        )
    assert [event.title for event in events] == ["Позвонить маме"]
    assert events[0].start_at.astimezone(MOSCOW).isoformat() == "2026-05-13T16:00:00+03:00"


async def test_действие_по_событию_идёт_в_план(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()
    await flow.send("/add Встреча сегодня 15:00-16:00 #работа")
    await flow.press("add:confirm")

    await flow.send("/today")
    markup = mock.last_markup()
    go_callback = next(
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
        if button["callback_data"].startswith("ev:go:")
    )
    await flow.press(go_callback)
    assert "в план" in mock.last_text() or "по плану" in mock.last_text()

    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        events = await schedule_repo.list_for_window(
            session, stored.id, NOW_UTC - timedelta(hours=1), NOW_UTC + timedelta(days=2)
        )
    assert events[0].status.value == "going"


async def test_настройки_показывают_значения_и_меняют_режим(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    await flow.press("menu:settings")
    text = mock.last_text()
    assert "Настройки" in text
    assert "Europe/Moscow" in text
    assert "23:00–08:00" in text

    await flow.press("set:mode:manual")
    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
    assert stored.tracking_mode.value == "manual"


async def test_сброс_данных_требует_подтверждения(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()
    await flow.send("/add Встреча сегодня 15:00-16:00 #работа")
    await flow.press("add:confirm")

    await flow.press("menu:settings")
    await flow.press("set:reset")
    assert "необратимо" in mock.last_text()

    await flow.press("set:reset:no")
    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        events = await schedule_repo.list_for_window(
            session, stored.id, NOW_UTC - timedelta(hours=1), NOW_UTC + timedelta(days=2)
        )
    assert len(events) == 1, "отказ от сброса не должен удалять данные"

    await flow.press("set:reset")
    await flow.press("set:reset:yes")
    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        events = await schedule_repo.list_for_window(
            session, stored.id, NOW_UTC - timedelta(hours=1), NOW_UTC + timedelta(days=2)
        )
        assert events == []
        assert stored.is_onboarded is False


async def test_mute_сохраняется_в_настройках(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.onboard()

    await flow.send("/mute 2h")
    assert "не спрашиваю" in mock.last_text()

    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        value = await settings_repo.get_value(session, stored.id, SettingKey.MUTE_UNTIL)
    assert value is not None
    assert datetime.fromisoformat(value) == NOW_UTC + timedelta(hours=2)

    await flow.send("/mute off")
    assert "Снова на связи" in mock.last_text()
    async with database.session() as session:
        stored = await users_repo.get_by_telegram_id(session, TG_USER.id)
        assert await settings_repo.get_value(session, stored.id, SettingKey.MUTE_UNTIL) is None


async def test_команды_справки(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.send("/help")
    assert "/mute 2h" in mock.last_text()

    await flow.send("/privacy")
    assert "Что я храню" in mock.last_text()

    await flow.send("абракадабра")
    assert "Не разобрал" in mock.last_text()


async def test_повторное_нажатие_не_дублируется(database, settings, clock) -> None:
    flow, mock = build_flow(database, settings, clock)
    await flow.send("/start")
    await flow.press("onb:tz:0")
    requests_after_first = len(mock.requests)

    # Тот же callback в окне дедупликации: рисуем только toast, без новых правок.
    message = mock.last_message()
    await flow.dispatcher.feed_update(
        flow.bot,
        Update(update_id=99, callback_query=button_press("onb:tz:0", message=message)),
    )
    assert len(mock.requests) == requests_after_first + 1


async def test_джоб_отправляет_напоминание(database, settings, user) -> None:
    mock = MockSession()
    bot = build_bot(mock)
    ctx = JobContext(bot=bot, database=database, settings=settings)

    async with database.session() as session:
        event = await schedule_service.create(
            session,
            user,
            title="Созвон",
            start_local=datetime(2026, 5, 12, 15, 0, tzinfo=MOSCOW),
            end_local=datetime(2026, 5, 12, 16, 0, tzinfo=MOSCOW),
            category="work",
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
        assert len(reminders) == 1
        # Делаем напоминание «созревшим»: оно должно было уйти в 14:45 МСК.
        reminders[0].send_at = NOW_UTC - timedelta(minutes=1)
        reminder_id = reminders[0].id

    assert await reminder_tick(ctx, now_utc=NOW_UTC) == 1
    assert "Через 15 мин: Созвон" in mock.last_text()
    assert mock.last_markup() is not None  # кнопки «Да / Нет / Позже»

    async with database.session() as session:
        stored_reminder = await reminders_repo.get_by_id(session, reminder_id)
    assert stored_reminder.status.value == "sent"

    # Повторный тик ничего не отправляет: идемпотентность.
    assert await reminder_tick(ctx, now_utc=NOW_UTC) == 0


async def test_джоб_откладывает_напоминание_в_тишину(database, settings, user) -> None:
    mock = MockSession()
    bot = build_bot(mock)
    ctx = JobContext(bot=bot, database=database, settings=settings)

    async with database.session() as session:
        await users_service.mute_for(session, user, timedelta(hours=2), now=NOW_UTC)
        event = await schedule_service.create(
            session,
            user,
            title="Ранняя встреча",
            start_local=datetime(2026, 5, 12, 15, 0, tzinfo=MOSCOW),
            end_local=datetime(2026, 5, 12, 16, 0, tzinfo=MOSCOW),
            reminder_offset=15,
            now_utc=NOW_UTC,
        )
        reminders = await reminders_repo.list_for_event(session, event.id)
        reminders[0].send_at = NOW_UTC - timedelta(minutes=1)
        reminder_id = reminders[0].id

    assert await reminder_tick(ctx, now_utc=NOW_UTC) == 0, "в тишине не отправляем"
    async with database.session() as session:
        stored = await reminders_repo.get_by_id(session, reminder_id)
    assert stored.status.value == "pending"
    assert stored.send_at > NOW_UTC  # отложено, а не потеряно
