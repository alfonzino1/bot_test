"""Тексты интерфейса: русская локаль.

Каталог — плоский словарь ``ключ → шаблон``. Плейсхолдеры в формате
``str.format``. Любой ключ обязан существовать здесь: тест
``tests/test_i18n_catalog.py`` проверяет, что все ``t("…")`` из кода есть в каталоге.

Тон текстов: тёплый, без осуждения, 1–2 эмодзи на сообщение (ТЗ, раздел 3).
"""

from __future__ import annotations

CATALOG: dict[str, str] = {
    # ── Общее ────────────────────────────────────────────────────────────────
    "common.btn_menu": "🏠 Меню",
    "common.btn_timer": "⏱ Старт/Стоп",
    "common.not_understood": "Не разобрал 🤔 Попробуй: завтра 15:00",
    "common.error": "Ой, что-то сломалось 😔 Уже записал в лог, попробуй ещё раз.",
    "common.cancel": "Отмена",
    "common.skip": "Пропустить",
    "common.later": "Позже",
    "common.back": "Назад",
    "common.done": "Готово",
    "common.yes": "Да",
    "common.no": "Нет",
    "common.saved": "✅ Записал",
    "common.deleted": "Убрал 🗑",
    "common.canceled": "Ок, отменил 👌",
    "common.throttled": "Секунду, уже обрабатываю 👌",
    "common.not_allowed": "Бот пока только для своих 🔒",
    "common.pick_from_buttons": "Выбери вариант кнопкой ниже 👇",
    "common.error_generic_cb": "Не получилось, попробуй ещё раз 🙏",

    # ── Форматирование значений ──────────────────────────────────────────────
    "plural.event.one": "событие",
    "plural.event.few": "события",
    "plural.event.many": "событий",
    "format.duration.hours_minutes": "{hours}ч {minutes}мин",
    "format.duration.hours": "{hours}ч",
    "format.duration.minutes": "{minutes}мин",
    "format.date.today": "сегодня",
    "format.date.tomorrow": "завтра",
    "format.date.day_after_tomorrow": "послезавтра",
    "format.date.yesterday": "вчера",
    "format.repeat.daily": "каждый день",
    "format.repeat.weekdays": "по будням",
    "format.repeat.weekly": "по {days}",

    # ── Онбординг ────────────────────────────────────────────────────────────
    "onboarding.step": "Шаг {step} из {total}",
    "onboarding.greeting": (
        "Привет! Я Хронос ⏳\n\n"
        "Помогу не забывать график и покажу, куда реально уходит время.\n"
        "Настроимся за минуту — три коротких вопроса."
    ),
    "onboarding.tz_title": "Шаг 1. Где ты по времени? 🌍",
    "onboarding.tz_hint": "Если твоего города нет — нажми «✏️ Другая» и напиши его.",
    "onboarding.tz_custom_prompt": "Напиши город или зону: например «Москва» или Asia/Almaty 🌍",
    "onboarding.tz_custom_button": "✏️ Другая",
    "onboarding.work_custom_button": "✏️ Свои часы",
    "onboarding.tz_unknown": "Не узнал такую зону 🤔 Попробуй ещё: «Казань», «Берлин», Europe/Moscow",
    "onboarding.tz_saved": "Запомнил: {tz} ✅",
    "onboarding.mode_title": "Шаг 2. Как удобнее следить за временем? ⏱",
    "onboarding.mode_hint": "Это можно поменять в настройках в любой момент.",
    "onboarding.mode_manual": "Сам жму Старт/Стоп",
    "onboarding.mode_auto": "Спрашивай меня",
    "onboarding.mode_both": "И то, и другое",
    "onboarding.mode_saved": "Понял, режим: {mode} ✅",
    "onboarding.work_title": "Шаг 3. В какие часы можно тебя беспокоить? 🔔",
    "onboarding.work_hint": "Вне этих часов я молчу. Ночью — тихо по умолчанию (23:00–8:00).",
    "onboarding.work_morning": "С 8 до 17",
    "onboarding.work_day": "С 10 до 19",
    "onboarding.work_evening": "С 12 до 21",
    "onboarding.work_custom_prompt": "Напиши интервал, например: 9:30-18:00 ⏰",
    "onboarding.work_saved": "Рабочие часы: {start}–{end} ✅",
    "onboarding.done": (
        "Готово! Я на связи 🎉\n\n"
        "Начни с главного: добавь первое событие или запусти таймер.\n"
        "Подсказка в любой момент — /help"
    ),

    # ── Главное меню ─────────────────────────────────────────────────────────
    "menu.title": "{name}, вот твоя картина дня 📊",
    "menu.title_anon": "Вот твоя картина дня 📊",
    "menu.summary": "📅 Сегодня: {events} · {focus} в фокусе",
    "menu.next_event": "Ближайшее: {time} — {title}",
    "menu.no_events": "На сегодня событий нет — свободный день 🌤",
    "menu.hint": "Что дальше?",
    "menu.btn_schedule": "📅 Расписание",
    "menu.btn_timer": "⏱ Таймер",
    "menu.btn_add": "➕ Добавить",
    "menu.btn_report": "📊 Отчёт",
    "menu.btn_settings": "⚙️ Настройки",
    "menu.focus_none": "0мин",

    # ── Расписание и события ─────────────────────────────────────────────────
    "today.title": "📅 Сегодня, {date}",
    "today.empty": "На сегодня пусто. Свободный день 🌤",
    "schedule.title": "📅 Расписание на неделю",
    "schedule.empty": "Пока пусто. Добавь первое событие кнопкой «➕ Добавить» 🌱",
    "schedule.day_header": "{weekday}, {date}",
    "schedule.line": "{start}–{end} · {title}",
    "schedule.hint": "Нажми на событие, чтобы отметить или перенести 👇",
    "schedule.btn_event": "{start} {title}",
    "schedule.status_going": "✅ идёшь",
    "schedule.status_late": "⏰ опоздаешь",
    "schedule.status_canceled": "❌ отменено",
    "schedule.status_moved": "🔄 перенесено",
    "event.card": "{emoji} {title}\n🕐 {start}–{end} · {date}\n{status}",
    "event.card_footer": "Что делаем?",
    "event.btn_going": "✅ Иду",
    "event.btn_late": "⏰ Опоздаю",
    "event.btn_cancel": "❌ Отменяю",
    "event.btn_move": "🔄 Перенести",
    "event.btn_delete": "🗑 Удалить",
    "event.btn_timer": "⏱ Таймер",
    "event.going_ok": "Отлично, иду в план ✅",
    "event.late_ok": "Понял, буду ждать к {time} 👌",
    "event.canceled_ok": "Ок, убрал из плана ❌",
    "event.deleted_ok": "Убрал событие 🗑",
    "event.move_prompt": "На когда перенести? Напиши, например: завтра 15:00 🔄",
    "event.moved_ok": "🔄 Перенёс на {when}",
    "event.not_found": "Не нашёл это событие — возможно, оно уже удалено 🤔",
    "event.status_planned": "🕓 по плану",
    "event.status_done": "✅ сделано",

    # ── Добавление события ───────────────────────────────────────────────────
    "add.wizard_title": "Как назовём событие? ✍️",
    "add.wizard_title_hint": "Например: Созвон с командой",
    "add.wizard_when": "Когда? 📆",
    "add.when_today": "Сегодня",
    "add.when_tomorrow": "Завтра",
    "add.when_date": "Другая дата",
    "add.when_repeat_daily": "Каждый день",
    "add.when_repeat_weekdays": "По будням",
    "add.when_repeat_weekly": "Каждую неделю",
    "add.when_date_prompt": "Напиши дату: 12.05, 2026-05-12 или «через 3 дня» 📆",
    "add.when_bad": "Не понял дату 🤔 Попробуй: 12.05 или завтра",
    "add.time_prompt": "Во сколько? 🕐",
    "add.time_prompt_hint": "Напиши время: 15:00 или 15:00-16:30",
    "add.time_bad": "Не понял время 🤔 Попробуй: 15:00 или 15:00-16:30",
    "add.time_whole_hour": "{hour}:00",
    "add.reminder_prompt": "Напомнить? ⏰",
    "add.reminder_immediate": "В момент",
    "add.reminder_15": "За 15 мин",
    "add.reminder_60": "За час",
    "add.reminder_off": "Не надо",
    "add.reminder_minutes": "За {minutes} мин",
    "add.reminder_hours": "За {hours} ч",
    "add.preview_title": "Проверь 👀",
    "add.preview_no_time": "время не выбрано",
    "add.preview_no_title": "(без названия)",
    "add.preview_line": "{emoji} {title}\n🕐 {when}\n🔔 {reminder}",
    "add.btn_confirm": "✅ Ок",
    "add.btn_restart": "✍️ Заново",
    "add.created": "✅ Записал: {title} — {when}",
    "add.usage": (
        "Быстрое добавление: напиши одной строкой —\n"
        "`/add Встреча завтра 15:00-16:00 #работа`\n\n"
        "Понимаю: сегодня, завтра, пн–вс, 12.05, «через 3 дня», "
        "«в 15:00», «15:00-16:30», «за 15 мин», «#учёба»."
    ),
    "add.overlap": "⚠️ Наложение с «{title}» в {start}–{end} — оставляю как есть.",

    # ── Напоминания ──────────────────────────────────────────────────────────
    "reminder.now": "⏰ Сейчас: {title}",
    "reminder.in_minutes": "⏰ Через {minutes} мин: {title}",
    "reminder.start_timer": "Запустить таймер?",
    "reminder.no_schedule": "Без события в расписании",
    "reminder.later_ok": "Ок, напомню через 10 минут 👌",
    "reminder.btn_yes": "⏱ Да, старт",
    "reminder.btn_no": "Нет",
    "reminder.btn_later": "Позже",
    "reminder.no_ok": "Ок, без таймера 👌",

    # ── Опросы о времени (модуль B, этап 4) ──────────────────────────────────
    "poll.context_question": "По плану сейчас: «{title}» ({start}–{end}). Запустить таймер?",
    "poll.passive_question": "Чем занят сейчас? ⏱",
    "poll.same_as_last": "🕐 То же, что час назад",
    "poll.skip_answer": "⏭ Пропустить",
    "poll.toast_saved": "✅ Записал",
    "poll.toast_skipped": "Ок, не спрашиваю 👌",
    "poll.toast_same": "✅ Записал, как в прошлый раз",

    # ── Таймер (модуль B, этап 2) ────────────────────────────────────────────
    "timer.coming_soon": "⏱ Таймер подключу на втором шаге — сейчас собираю расписание 🛠",

    # ── Отчёты (модуль C, этап 3) ────────────────────────────────────────────
    "report.coming_soon": "📊 Отчёты собираю на третьем шаге. Уже показываю фокус дня в меню 😉",

    # ── Тишина ───────────────────────────────────────────────────────────────
    "mute.ok": "Ок, не спрашиваю 👌 до {until}",
    "mute.off": "Снова на связи 👋",
    "mute.usage": "Не понял 🤔 Попробуй: /mute 2h или /mute 30m",

    # ── Настройки ────────────────────────────────────────────────────────────
    "settings.title": "⚙️ Настройки",
    "settings.body": (
        "🌍 Зона: {tz}\n"
        "🔔 Беспокоить: {work_start}–{work_end}\n"
        "🌙 Тихий час: {quiet_start}–{quiet_end}\n"
        "⏱ Режим: {mode}\n"
        "📊 Отчёты: {reports}\n"
        "🔇 Тишина: {mute}"
    ),
    "settings.btn_tz": "🌍 Зона",
    "settings.btn_work": "🔔 Рабочие часы",
    "settings.btn_quiet": "🌙 Тихий час",
    "settings.btn_mode": "⏱ Режим трекинга",
    "settings.btn_reports": "📊 Отчёты",
    "settings.btn_reset": "🗑 Сбросить данные",
    "settings.reports_off": "выключены",
    "settings.reports_daily": "каждый вечер",
    "settings.reports_weekly": "раз в неделю",
    "settings.mute_off": "нет",
    "settings.mute_until": "до {until}",
    "settings.ask_tz": "Напиши город или зону 🌍",
    "settings.ask_work": "Напиши рабочие часы, например 9:30-18:00 ⏰",
    "settings.ask_quiet": "Напиши тихий час, например 23:00-8:00 🌙",
    "settings.interval_bad": "Не понял интервал 🤔 Попробуй так: 9:30-18:00",
    "settings.saved": "Готово 👌",
    "settings.ask_mode": "Как следим за временем? ⏱",
    "settings.ask_reports": "Как часто присылать итоги? 📊",
    "settings.btn_reports_daily": "Каждый вечер",
    "settings.btn_reports_weekly": "Раз в неделю",
    "settings.btn_reports_off": "Не присылать",
    "settings.reset_confirm": (
        "Удалю все события, записи времени и настройки. Это необратимо.\nТочно?"
    ),
    "settings.btn_reset_yes": "🗑 Да, удалить",
    "settings.btn_reset_no": "Оставить",
    "settings.reset_done": "Всё удалил. Начнём с чистого листа 🌱",

    # ── Справка и приватность ────────────────────────────────────────────────
    "help.title": "Что я умею 🧭",
    "help.body": (
        "/menu — главное меню\n"
        "/today — расписание на сегодня\n"
        "/add — быстрое добавление события\n"
        "/week — отчёт за неделю\n"
        "/start — таймер: старт\n"
        "/stop — таймер: стоп\n"
        "/mute 2h — помолчать два часа\n"
        "/privacy — что я храню\n\n"
        "Всё, что можно, делается кнопкой 👇"
    ),
    "privacy.title": "🔒 Что я храню",
    "privacy.body": (
        "Только твои события, записи времени и настройки — и всё.\n\n"
        "• Данные лежат в базе на твоём сервере, наружу не уходят.\n"
        "• Никакой аналитики третьих сторон и рекламы.\n"
        "• «Сбросить данные» в настройках удаляет всё без остатка.\n\n"
        "Твоё время — твоё дело 🤝"
    ),

    # ── Ошибки и ограничения ─────────────────────────────────────────────────
    "errors.db": "Не смог достучаться до базы 😔 Попробуй через минуту.",
    "errors.forbidden": "Это действие не для тебя 🔒",
    "errors.event_gone": "Событие уже неактуально 🤷",
    "errors.timezone": "Не смог разобрать зону, оставил прежнюю.",
}
