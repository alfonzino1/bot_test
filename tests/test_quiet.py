"""Тесты «тишины»: тихий час, рабочие часы, ручной mute (docs/DECISIONS.md D-09)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from chronos.constants import SettingKey
from chronos.models import User
from chronos.services import quiet

MOSCOW = ZoneInfo("Europe/Moscow")


def _user() -> User:
    """Пользователь с настройками по умолчанию (без сохранения в БД)."""
    return User(
        id=1,
        telegram_id=1,
        tz="Europe/Moscow",
        work_start=time(10, 0),
        work_end=time(19, 0),
        quiet_start=time(23, 0),
        quiet_end=time(8, 0),
    )


def _utc(hour: int, minute: int = 0, *, day: int = 12) -> datetime:
    """Момент UTC, соответствующий московскому времени (UTC+3)."""
    return datetime(2026, 5, day, hour, minute, tzinfo=MOSCOW).astimezone(UTC)


def test_тихий_час_идёт_через_полночь() -> None:
    user = _user()
    assert quiet.is_quiet_now(user, now_utc=_utc(2, 0)) is True
    assert quiet.is_quiet_now(user, now_utc=_utc(7, 59)) is True
    assert quiet.is_quiet_now(user, now_utc=_utc(8, 0)) is False
    assert quiet.is_quiet_now(user, now_utc=_utc(22, 59)) is False
    assert quiet.is_quiet_now(user, now_utc=_utc(23, 30)) is True


def test_рабочие_часы() -> None:
    user = _user()
    assert quiet.is_work_time(user, now_utc=_utc(12, 0)) is True
    assert quiet.is_work_time(user, now_utc=_utc(9, 59)) is False
    assert quiet.is_work_time(user, now_utc=_utc(19, 0)) is False


def test_ручная_тишина_подавляет_и_истекает() -> None:
    now = _utc(12, 0)
    settings = {SettingKey.MUTE_UNTIL.value: (now + timedelta(hours=2)).isoformat()}
    assert quiet.is_muted(settings, now_utc=now) is True
    assert quiet.is_silent(_user(), settings, now_utc=now) is True

    expired = {SettingKey.MUTE_UNTIL.value: (now - timedelta(minutes=1)).isoformat()}
    assert quiet.is_muted(expired, now_utc=now) is False


def test_битая_настройка_тишины_не_ломает_бота() -> None:
    settings = {SettingKey.MUTE_UNTIL.value: "не-дата"}
    assert quiet.mute_until(settings) is None
    assert quiet.is_muted(settings, now_utc=_utc(12, 0)) is False


def test_следующий_разрешённый_момент_это_конец_тихого_часа() -> None:
    user = _user()
    night = _utc(2, 0)
    allowed = quiet.next_allowed_moment(user, {}, now_utc=night)
    assert allowed == _utc(8, 0)


def test_следующий_разрешённый_момент_учитывает_mute() -> None:
    user = _user()
    now = _utc(12, 0)
    until = now + timedelta(hours=3)
    allowed = quiet.next_allowed_moment(
        user, {SettingKey.MUTE_UNTIL.value: until.isoformat()}, now_utc=now
    )
    assert allowed == until


def test_дневной_момент_не_сдвигается() -> None:
    user = _user()
    now = _utc(12, 0)
    assert quiet.next_allowed_moment(user, {}, now_utc=now) == now


def test_пассивный_опрос_только_в_рабочие_часы() -> None:
    user = _user()
    assert quiet.can_ask_passively(user, {}, now_utc=_utc(12, 0)) is True
    assert quiet.can_ask_passively(user, {}, now_utc=_utc(2, 0)) is False
    assert quiet.can_ask_passively(user, {}, now_utc=_utc(21, 0)) is False


def test_описание_тишины_для_настроек() -> None:
    user = _user()
    now = _utc(12, 0)
    until = now + timedelta(hours=1)
    text = quiet.describe_silence(
        user, {SettingKey.MUTE_UNTIL.value: until.isoformat()}, now_utc=now
    )
    assert text is not None and "13:00" in text
