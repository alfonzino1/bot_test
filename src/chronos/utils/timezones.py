"""Таймзоны: популярные варианты для кнопок и разбор текстового ввода.

Геолокация не используется (см. docs/DECISIONS.md D-04): кнопки + текстовый
fallback. ``zoneinfo`` работает за счёт пакета ``tzdata`` (в зависимостях).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class TimezoneOption:
    """Вариант таймзоны для кнопки онбординга/настроек."""

    label: str
    iana: str
    emoji: str = "🌍"


#: Порядок соответствует частотности аудитории: СНГ → популярные релокации.
COMMON_TIMEZONES: tuple[TimezoneOption, ...] = (
    TimezoneOption("Москва", "Europe/Moscow", "🇷🇺"),
    TimezoneOption("Санкт-Петербург", "Europe/Moscow", "🇷🇺"),
    TimezoneOption("Калининград", "Europe/Kaliningrad", "🇷🇺"),
    TimezoneOption("Самара", "Europe/Samara", "🇷🇺"),
    TimezoneOption("Екатеринбург", "Asia/Yekaterinburg", "🇷🇺"),
    TimezoneOption("Омск", "Asia/Omsk", "🇷🇺"),
    TimezoneOption("Новосибирск", "Asia/Novosibirsk", "🇷🇺"),
    TimezoneOption("Красноярск", "Asia/Krasnoyarsk", "🇷🇺"),
    TimezoneOption("Иркутск", "Asia/Irkutsk", "🇷🇺"),
    TimezoneOption("Владивосток", "Asia/Vladivostok", "🇷🇺"),
    TimezoneOption("Киев", "Europe/Kyiv", "🇺🇦"),
    TimezoneOption("Минск", "Europe/Minsk", "🇧🇾"),
    TimezoneOption("Алматы", "Asia/Almaty", "🇰🇿"),
    TimezoneOption("Астана", "Asia/Almaty", "🇰🇿"),
    TimezoneOption("Ташкент", "Asia/Tashkent", "🇺🇿"),
    TimezoneOption("Бишкек", "Asia/Bishkek", "🇰🇬"),
    TimezoneOption("Душанбе", "Asia/Dushanbe", "🇹🇯"),
    TimezoneOption("Ереван", "Asia/Yerevan", "🇦🇲"),
    TimezoneOption("Тбилиси", "Asia/Tbilisi", "🇬🇪"),
    TimezoneOption("Баку", "Asia/Baku", "🇦🇿"),
    TimezoneOption("Стамбул", "Europe/Istanbul", "🇹🇷"),
    TimezoneOption("Дубай", "Asia/Dubai", "🇦🇪"),
    TimezoneOption("Бангкок", "Asia/Bangkok", "🇹🇭"),
    TimezoneOption("Берлин", "Europe/Berlin", "🇩🇪"),
    TimezoneOption("Прага", "Europe/Prague", "🇨🇿"),
    TimezoneOption("Варшава", "Europe/Warsaw", "🇵🇱"),
    TimezoneOption("Лондон", "Europe/London", "🇬🇧"),
    TimezoneOption("Нью-Йорк", "America/New_York", "🇺🇸"),
    TimezoneOption("Лос-Анджелес", "America/Los_Angeles", "🇺🇸"),
    TimezoneOption("Токио", "Asia/Tokyo", "🇯🇵"),
    TimezoneOption("Сеул", "Asia/Seoul", "🇰🇷"),
)

#: Русские и латинские названия городов → IANA. Ключи в нижнем регистре.
CITY_ALIASES: dict[str, str] = {
    "москва": "Europe/Moscow",
    "moscow": "Europe/Moscow",
    "мск": "Europe/Moscow",
    "питер": "Europe/Moscow",
    "спб": "Europe/Moscow",
    "санкт-петербург": "Europe/Moscow",
    "st petersburg": "Europe/Moscow",
    "saint petersburg": "Europe/Moscow",
    "калининград": "Europe/Kaliningrad",
    "самара": "Europe/Samara",
    "екатеринбург": "Asia/Yekaterinburg",
    "омск": "Asia/Omsk",
    "новосибирск": "Asia/Novosibirsk",
    "красноярск": "Asia/Krasnoyarsk",
    "иркутск": "Asia/Irkutsk",
    "владивосток": "Asia/Vladivostok",
    "киев": "Europe/Kyiv",
    "kyiv": "Europe/Kyiv",
    "kiev": "Europe/Kyiv",
    "минск": "Europe/Minsk",
    "алматы": "Asia/Almaty",
    "алма-ата": "Asia/Almaty",
    "астана": "Asia/Almaty",
    "нур-султан": "Asia/Almaty",
    "ташкент": "Asia/Tashkent",
    "бишкек": "Asia/Bishkek",
    "душанбе": "Asia/Dushanbe",
    "ереван": "Asia/Yerevan",
    "тбилиси": "Asia/Tbilisi",
    "казань": "Europe/Moscow",
    "уфа": "Asia/Yekaterinburg",
    "пермь": "Asia/Yekaterinburg",
    "челябинск": "Asia/Yekaterinburg",
    "тюмень": "Asia/Yekaterinburg",
    "волгоград": "Europe/Volgograd",
    "ростов-на-дону": "Europe/Moscow",
    "краснодар": "Europe/Moscow",
    "сочи": "Europe/Moscow",
    "воронеж": "Europe/Moscow",
    "нижний новгород": "Europe/Moscow",
    "саратов": "Europe/Saratov",
    "барнаул": "Asia/Barnaul",
    "томск": "Asia/Tomsk",
    "хабаровск": "Asia/Vladivostok",
    "якутск": "Asia/Yakutsk",
    "мурманск": "Europe/Moscow",
    "архангельск": "Europe/Moscow",
    "симферополь": "Europe/Simferopol",
    "севастополь": "Europe/Simferopol",
    "днепр": "Europe/Kyiv",
    "харьков": "Europe/Kyiv",
    "одесса": "Europe/Kyiv",
    "львов": "Europe/Kyiv",
    "гомель": "Europe/Minsk",
    "брест": "Europe/Minsk",
    "гродно": "Europe/Minsk",
    "витебск": "Europe/Minsk",
    "могилев": "Europe/Minsk",
    "шымкент": "Asia/Almaty",
    "караганда": "Asia/Almaty",
    "актау": "Asia/Aqtau",
    "атырау": "Asia/Atyrau",
    "самарканд": "Asia/Samarkand",
    "бухара": "Asia/Samarkand",
    "наманган": "Asia/Tashkent",
    "андорра": "Europe/Madrid",
    "баку": "Asia/Baku",
    "стамбул": "Europe/Istanbul",
    "istanbul": "Europe/Istanbul",
    "дубай": "Asia/Dubai",
    "dubai": "Asia/Dubai",
    "бангкок": "Asia/Bangkok",
    "пхукет": "Asia/Bangkok",
    "берлин": "Europe/Berlin",
    "berlin": "Europe/Berlin",
    "прага": "Europe/Prague",
    "варшава": "Europe/Warsaw",
    "лондон": "Europe/London",
    "нью-йорк": "America/New_York",
    "нью йорк": "America/New_York",
    "лос-анджелес": "America/Los_Angeles",
    "токио": "Asia/Tokyo",
    "сеул": "Asia/Seoul",
    "хельсинки": "Europe/Helsinki",
    "лиссабон": "Europe/Lisbon",
    "барселона": "Europe/Madrid",
    "мадрид": "Europe/Madrid",
    "рим": "Europe/Rome",
    "париж": "Europe/Paris",
    "амстердам": "Europe/Amsterdam",
    "тиват": "Europe/Podgorica",
    "белград": "Europe/Belgrade",
    "софия": "Europe/Sofia",
    "бухарест": "Europe/Bucharest",
    "будапешт": "Europe/Budapest",
    "вена": "Europe/Vienna",
    "цюрих": "Europe/Zurich",
    "тель-авив": "Asia/Jerusalem",
    "иерусалим": "Asia/Jerusalem",
    "бейрут": "Asia/Beirut",
    "дели": "Asia/Kolkata",
    "мумбаи": "Asia/Kolkata",
    "шанхай": "Asia/Shanghai",
    "пекин": "Asia/Shanghai",
    "гонконг": "Asia/Hong_Kong",
    "сингапур": "Asia/Singapore",
    "бали": "Asia/Makassar",
    "джакарта": "Asia/Jakarta",
    "сидней": "Australia/Sydney",
    "мельбурн": "Australia/Melbourne",
    "торонто": "America/Toronto",
    "чикаго": "America/Chicago",
    "мехико": "America/Mexico_City",
    "сан-паулу": "America/Sao_Paulo",
    "буэнос-айрес": "America/Argentina/Buenos_Aires",
    "каир": "Africa/Cairo",
    "кейптаун": "Africa/Johannesburg",
    "найроби": "Africa/Nairobi",
    "тбилиси": "Asia/Tbilisi",
}

#: Смещения вида «UTC+3» / «GMT+3» → ближайшая стабильная зона. Ключ — смещение в часах.
_STATIC_OFFSET_ZONES: dict[int, str] = {
    -11: "Pacific/Pago_Pago",
    -10: "Pacific/Honolulu",
    -9: "America/Anchorage",
    -8: "America/Los_Angeles",
    -7: "America/Denver",
    -6: "America/Chicago",
    -5: "America/New_York",
    -4: "America/Santiago",
    -3: "America/Sao_Paulo",
    -2: "America/Noronha",
    0: "UTC",
    1: "Europe/Berlin",
    2: "Europe/Kaliningrad",
    3: "Europe/Moscow",
    4: "Asia/Samara",
    5: "Asia/Yekaterinburg",
    6: "Asia/Omsk",
    7: "Asia/Krasnoyarsk",
    8: "Asia/Irkutsk",
    9: "Asia/Yakutsk",
    10: "Asia/Vladivostok",
    11: "Asia/Magadan",
    12: "Asia/Kamchatka",
}


@lru_cache(maxsize=256)
def tz_for(name: str | None, fallback: str = "Europe/Moscow") -> ZoneInfo:
    """Зона по IANA-имени; при неудаче — ``fallback`` (никогда не падаем)."""
    for candidate in (name, fallback, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


def resolve_timezone(text: str | None) -> ZoneInfo | None:
    """Разбирает текст пользователя в таймзону: IANA, город или «UTC+3».

    Возвращает ``None``, если понять не удалось — вызывающий код покажет подсказку.
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None

    # 1. Прямое IANA-имя (Europe/Moscow, Asia/Almaty).
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError):
        pass

    # 2. Смещение UTC+3 / GMT+3 / +03:00.
    normalized = raw.lower().replace(" ", "")
    for prefix in ("utc", "gmt", "мск", "gmt"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    if normalized.startswith(("+", "-")):
        try:
            hours = int(normalized.split(":")[0])
        except ValueError:
            hours = 99
        zone = _STATIC_OFFSET_ZONES.get(hours)
        if zone:
            return ZoneInfo(zone)

    # 3. Город/алиас из словаря.
    key = raw.lower().strip()
    if key in CITY_ALIASES:
        return ZoneInfo(CITY_ALIASES[key])

    # 4. Частичное совпадение по городу: «москва, россия» → москва.
    for alias, iana in CITY_ALIASES.items():
        if alias in key:
            return ZoneInfo(iana)

    # 5. Последняя часть IANA-пути как город: «Almaty».
    capital = raw.split("/")[-1].replace("_", " ").strip().lower()
    if capital in CITY_ALIASES:
        return ZoneInfo(CITY_ALIASES[capital])

    return None


def local_now(tz: ZoneInfo) -> datetime:
    """Текущий момент в локальной зоне пользователя (aware)."""
    return datetime.now(tz)


def to_local(moment: datetime, tz: ZoneInfo) -> datetime:
    """UTC → локальное время пользователя. Naive трактуется как UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC).astimezone(tz)
    return moment.astimezone(tz)


def to_utc(moment: datetime) -> datetime:
    """Локальное (или любое aware) время → UTC. Naive — ошибка: зона неизвестна."""
    if moment.tzinfo is None:
        raise ValueError("Нельзя конвертировать naive-datetime в UTC: неизвестна зона")
    return moment.astimezone(UTC)


def day_bounds_local(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Границы локальных суток ``[00:00; 00:00 следующего дня)`` в зоне пользователя."""
    start = datetime.combine(day, time.min).replace(tzinfo=tz)
    return start, start + timedelta(days=1)


def is_within(moment: time, start: time, end: time) -> bool:
    """Попадает ли время суток в интервал; интервал может идти через полночь."""
    if start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def interval_length_minutes(start: time, end: time) -> int:
    """Длина интервала времени суток в минутах (учитывает переход через полночь)."""
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    return end_minutes - start_minutes


def tz_name(tz: ZoneInfo) -> str:
    """Имя зоны для хранения в БД."""
    return getattr(tz, "key", None) or str(tz)


def app_zone() -> ZoneInfo:
    """Зона приложения по умолчанию (до онбординга пользователя)."""
    from chronos.config import get_settings

    return tz_for(get_settings().default_timezone)


__all__ = [
    "CITY_ALIASES",
    "COMMON_TIMEZONES",
    "TimezoneOption",
    "app_zone",
    "day_bounds_local",
    "interval_length_minutes",
    "is_within",
    "local_now",
    "resolve_timezone",
    "to_local",
    "to_utc",
    "tz_for",
    "tz_name",
]
