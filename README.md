# Хронос ⏳

Личный трекер графика и времени с аналитикой для Telegram.

Ключевая фишка — **связка двух модулей**: расписание само предлагает запустить
таймер, когда по плану началось событие, а по итогам недели бот показывает
«план vs факт».

* Платформа: Telegram (aiogram 3.x), Python 3.11+
* Язык интерфейса: русский (`i18n/ru.py`, каталог готов к другим локалям)
* Аудитория: single-user MVP, схема готова к мультиюзеру (всё по `user_id`)
* Статус: **Этап 1 готов** (онбординг, расписание, напоминания, `/add`, `/today`,
  настройки, БД и миграции) + каркас под этапы 2–4

---

## 1. Быстрый старт

### Самый короткий путь (Windows / Linux)

```powershell
cd chronos
notepad .env          # вставь BOT_TOKEN от @BotFather (одна строка)
.\run.ps1 migrate     # создаёт схему БД
.\run.ps1 doctor      # самопроверка: конфиг, БД, тексты
.\run.ps1             # запуск бота; остановка — Ctrl+C
```

```bash
# Linux / VPS — то же самое
./run.sh migrate && ./run.sh doctor && ./run.sh
```

Обёртка `run.ps1` / `run.sh` сама выставляет `PYTHONPATH`, подхватывает `.venv`
(если он есть) и умеет всё нужное: `run` (по умолчанию), `doctor`, `migrate`,
`migrate-history`, `test`. Дальше в Telegram: открой своего бота и отправь `/start`.

### Классический вариант с venv

```bash
cd chronos
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # или: pip install -e ".[dev]"

cp .env.example .env        # вставь BOT_TOKEN от @BotFather
alembic upgrade head        # создаёт схему БД
python -m chronos doctor    # самопроверка: конфиг, БД, тексты
python -m chronos           # запуск бота (long polling)
```

Что происходит при запуске (видно в логах):

```
INFO | chronos.services.users | Новый пользователь: telegram_id=…
INFO | __main__:run_bot:50     | Хронос запущен: локаль=ru задач=1
```

Логи: `data/chronos.log` (ротация 10 МБ × 5), база: `data/chronos.db`.
Если токена нет — `doctor` скажет об этом прямо, а бот завершится с кодом 2;
если токен неверный, Telegram ответит `TelegramUnauthorizedError: Unauthorized`.

Отдельно: `migrations/` — Alembic с самого начала (см. ниже), поэтому схему
создаёт именно `alembic upgrade head`, а не «магия» в рантайме.

### Переменные окружения (`.env`)

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | токен бота (обязателен) | — |
| `DATABASE_URL` | строка подключения | SQLite `data/chronos.db` (абсолютный путь подставляет код) |
| `DEFAULT_TIMEZONE` | зона до онбординга | `Europe/Moscow` |
| `ALLOWED_TELEGRAM_IDS` | белый список (мультиюзер-задел) | пусто = открыт |
| `LOG_LEVEL`, `LOG_ENQUEUE` | логирование | `INFO`, `false` |
| `MORNING_DIGEST_AT`, `EVENING_DIGEST_AT`, `AUTOSTOP_AT`, `WEEKLY_REPORT_AT` | времена задач | `08:00`, `20:30`, `23:00`, `09:00` |
| `REMINDER_HORIZON_DAYS` | на сколько дней вперёд материализуются напоминания | `7` |

Секреты живут только в `.env`; в коде и логах токена нет.

### Запуск на Linux (VPS / Railway / Render)

**1. Системные зависимости** (Debian/Ubuntu, нужен Python 3.11+):

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
python3 --version          # должно быть 3.11 или новее
```

**2. Перенеси проект и поставь зависимости:**

```bash
sudo mkdir -p /opt/chronos && sudo chown "$USER" /opt/chronos
git clone <адрес-репозитория> /opt/chronos     # либо: rsync -av chronos/ user@host:/opt/chronos/
cd /opt/chronos
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt                 # + matplotlib, когда понадобятся графики
chmod +x run.sh                                 # скрипт уже в LF — просто даём право на запуск
```

**3. Настрой `.env`** — тот же файл, что и на Windows:

```bash
cp .env.example .env
nano .env            # BOT_TOKEN=... (обязательно)
```

**4. Запусти:**

```bash
./run.sh migrate     # создаёт схему БД в ./data/chronos.db
./run.sh doctor      # самопроверка: ждём "Всё готово ✅"
./run.sh             # бот. Остановить — Ctrl+C
```

Одной командой для первой проверки: `./run.sh migrate && ./run.sh doctor && ./run.sh`

**5. Чтобы работал постоянно** — systemd (готовый unit лежит в `deploy/chronos.service`):

```bash
sudo useradd -r -s /usr/sbin/nologin chronos 2>/dev/null || true   # отдельный сервисный юзер
sudo chown -R chronos:chronos /opt/chronos
sudo cp deploy/chronos.service /etc/systemd/system/chronos.service
sudo nano /etc/systemd/system/chronos.service     # поправь User/WorkingDirectory, если путь другой
sudo systemctl daemon-reload
sudo systemctl enable --now chronos
systemctl status chronos                          # состояние
journalctl -u chronos -f                          # живые логи
```

`ExecStartPre` сам применяет `alembic upgrade head` перед стартом, `Restart=always`
поднимает бота после падений/перезагрузки, а процессу разрешена запись только в `data/`.
Входящие порты открывать **не нужно** — long polling ходит исходящим соединением к
`api.telegram.org`, поэтому домен и HTTPS не требуются.

**Быстрая альтернатива без systemd** (переживёт разрыв SSH):

```bash
tmux new -s chronos './run.sh'        # отключиться: Ctrl+B, D; вернуться: tmux attach -t chronos
# или
nohup ./run.sh > data/nohup.log 2>&1 &
```

**Railway / Render / Fly.io** (там SQLite не переживает перезапуск):

| Параметр | Значение |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Pre-deploy / Release command | `alembic upgrade head` |
| Start command | `python -m chronos` |
| Переменные | `BOT_TOKEN`, `PYTHONPATH=src`, `DATABASE_URL=postgresql+asyncpg://…` |
| Зависимости для Postgres | добавить в проект extra `postgres` (`asyncpg`, `psycopg[binary]`) |

Файловая система Railway/Render эфемерна, поэтому на таких хостингах сразу бери
Postgres-плагин: код к нему готов — `repositories/` не меняется, меняется только
`DATABASE_URL` (Alembic подхватит его сам через `migrations/env.py`).

**Чек-лист «запустилось ли»:**

```bash
./run.sh doctor                    # ждём "Всё готово ✅"
journalctl -u chronos -n 30        # ожидаем: "Хронос запущен: локаль=ru задач=1"
ls -la data/                       # появились chronos.db и chronos.log
```

Затем в Telegram: открой своего бота → `/start` → онбординг → `/add Встреча завтра 15:00-16:00 #работа`.

---

## 2. План файлов

```
chronos/
├── run.ps1                   обёртка запуска для Windows (run|doctor|migrate|test)
├── run.sh                    обёртка запуска для Linux/macOS
├── pyproject.toml            зависимости, pytest, ruff
├── requirements.txt          прод-зависимости
├── alembic.ini               конфиг миграций
├── .env.example              шаблон конфигурации
├── migrations/
│   ├── env.py                асинхронный Alembic + метаданные моделей
│   ├── script.py.mako        шаблон ревизий
│   └── versions/…_initial_schema.py   первая миграция (все 6 таблиц)
├── docs/
│   └── DECISIONS.md          ADR: как разрешены противоречия ТЗ
├── deploy/
│   └── chronos.service       unit systemd для Linux/VPS
├── src/chronos/
│   ├── __main__.py           CLI: `run` (бот) и `doctor` (самопроверка)
│   ├── config.py             pydantic-settings + .env
│   ├── constants.py          enum'ы, категории, callback-namespace'ы, дефолты
│   ├── logging_setup.py      loguru: stderr + файл с ротацией
│   ├── i18n/
│   │   ├── __init__.py       t(), set_locale(), каталоги локалей
│   │   └── ru.py             182 текста: микрокопирайт ТЗ + подсказки
│   ├── models/               SQLAlchemy 2.0: user, schedule, time_log, poll(reminder), setting
│   │   └── types.py          UTCDateTime — все метки в UTC, всегда aware
│   ├── repositories/         единственное место с SQL (users, schedule, time_logs,
│   │                         reminders, polls, settings)
│   ├── services/             вся бизнес-логика
│   │   ├── schedule.py       создание/перенос событий, вхождения серий, напоминания
│   │   ├── analytics.py      отчёты: категории, план vs факт, тренды, пики
│   │   ├── quiet.py          тихий час / рабочие часы / mute — единая точка правды
│   │   ├── reminders.py      подбор готовых напоминаний + тексты
│   │   ├── users.py          онбординг, настройки, сброс данных
│   │   ├── drafts.py         черновик события для мастера (FSM-совместимый)
│   │   └── menu.py           сводка дня для главного меню
│   ├── utils/
│   │   ├── datetime_parser.py  «завтра 15:00-16:00 #работа» → черновик
│   │   ├── recurrence.py       правила повтора и вычисление вхождений
│   │   ├── timezones.py        города/IANA/UTC+N, конвертация UTC↔локаль
│   │   ├── formatting.py       «1ч 12мин», «завтра 15:00», склонения
│   │   └── db.py               движок, сессии, PRAGMA foreign_keys
│   ├── jobs/                 APScheduler: context, reminders (тик раз в минуту), scheduler
│   └── bot/
│       ├── dispatcher.py     сборка Dispatcher, порядок роутеров и мидлварей
│       ├── states.py         FSM-состояния сценариев
│       ├── texts.py          тексты reply-кнопок (для фильтров)
│       ├── middlewares/      context (время/настройки), db (сессия), user, throttle, errors
│       ├── keyboards/        reply (2 кнопки) и inline (всё ситуативное)
│       └── handlers/         onboarding, menu, add, schedule, settings,
│                             commands, reminders, errors, ui (одно сообщение)
└── tests/                    113 тестов, в т.ч. сквозные сценарии через MockSession
```

Принципы, заложенные в структуру:

* **Хендлер тонкий** — валидирует ввод, зовёт сервис, рисует ответ. SQL только в репозиториях.
* **Все действия идемпотентны** — уникальные ключи БД (`reminders(schedule_id, occurrence_start_at)`,
  `polls(user_id, kind, slot_at)`, частичный уникальный индекс «один активный таймер»).
* **Время в UTC** — `UTCDateTime` не принимает naive-datetime; конвертация на границе.
* **Нет магических строк** — коды и тексты живут в `constants.py` и `i18n/`.
* **Ошибки** — в лог и вежливым сообщением пользователю (`middlewares/errors.py`).

---

## 3. Схема БД

```
users            id, telegram_id, name, tz, work_start, work_end, quiet_start,
                 quiet_end, tracking_mode, onboarded_at, created_at, updated_at
schedule         id, user_id→users, title, start_at, end_at, repeat_rule, category,
                 reminder_offset, status, exceptions(JSON), message_id, created_at, updated_at
time_logs        id, user_id→users, category, start_at, end_at(NULL = таймер идёт),
                 note, source, schedule_id→schedule, message_id, created_at, updated_at
reminders        id, user_id→users, schedule_id→schedule, occurrence_start_at, send_at,
                 status, sent_at, created_at
polls            id, user_id→users, kind, slot_at, sent_at, answered_at, answer,
                 status, schedule_id→schedule, message_id, created_at
settings         user_id→users (PK), key (PK), value, updated_at
```

Что добавлено к схеме из ТЗ и почему — в [docs/DECISIONS.md](docs/DECISIONS.md):

| Решение | Кратко |
|---|---|
| D-01 | `/start` = онбординг (первый раз) → меню; таймер на кнопке/`/timer` |
| D-02 | `users` — источник правды по «горячим» настройкам; `settings` — для остального |
| D-03 | «Фокус» = 💼 Работа + 📚 Учёба (+ свои метки) |
| D-05 | Активный таймер = `time_logs.end_at IS NULL`, уникально на пользователя |
| D-06 | `message_id` в `time_logs`/`polls` — правило одного редактируемого сообщения |
| D-07 | `repeat_rule` (RFC 5545-подмножество) + `exceptions`: перенос одного вхождения не ломает серию |
| D-08 | `UTCDateTime`: в БД UTC, на выходе aware |
| D-09 | `mute_until` подавляет всё; тихий час — только проактивные сообщения |
| D-10 | План = минуты событий (кроме отменённых), факт = минуты `time_logs` |

---

## 4. Что уже работает (Этап 1)

**Онбординг** (≤ 60 секунд): привет → таймзона (кнопки городов + «✏️ Другая» →
парсер «Москва»/`Asia/Almaty`/`UTC+3`) → режим трекинга → рабочие часы → «Готово»
+ постоянная reply-клавиатура «🏠 Меню / ⏱ Старт/Стоп».

**Главное меню**: «📅 Сегодня: N событий · Xч Yмин в фокусе», ближайшее событие,
кнопки [📅 Расписание] [⏱ Таймер] [➕ Добавить] [📊 Отчёт] [⚙️ Настройки].

**Добавление события**:
* быстрое — `/add Встреча завтра 15:00-16:00 #работа` → превью → «✅ Ок»;
* мастер — название → когда (сегодня/завтра/дата/каждый день/по будням/каждую неделю) →
  во сколько → напомнить → превью → «✅ Ок»;
* понимает: `сегодня/завтра/послезавтра`, `через 3 дня`, `через 2 часа`, `12.05`,
  `2026-05-12`, `в пн`, `утром/днём/вечером`, `15:00-16:30`, `15.30`, `#метка`,
  `за 15 мин`, `за час`, `без напоминания`; предупреждает о наложении.

**Расписание и напоминания**: `/today` (карточки с кнопками ✅ Иду / ⏰ Опоздаю /
❌ Отменяю / 🔄 Перенести), экран недели, перенос одного вхождения серии,
фоновый тик раз в минуту отправляет напоминания «⏰ Через 15 мин: Созвон» с кнопками
«⏱ Да, старт / Нет / Позже»; в тихий час напоминание **откладывается, а не теряется**.

**Настройки**: таймзона, рабочие часы, тихий час, режим трекинга, частота отчётов,
сброс данных с подтверждением. Команды: `/menu`, `/today`, `/add`, `/mute 2h`
(+`/mute off`), `/help`, `/privacy`, `/timer`, `/stop`, `/week`.

Честные заглушки этапа 1 (сообщают о сроках, не ломая UX): `⏱ Таймер` и `📊 Отчёт`.

---

## 5. Тесты

```bash
pytest              # 113 тестов, ~13 секунд
```

| Файл | Что проверяет |
|---|---|
| `test_datetime_parser.py` | разбор дат/времени/интервалов/длительностей, «не тупи»-правила |
| `test_recurrence.py` | правила повтора, вхождения, исключения, границы окна |
| `test_analytics.py` | разрезы, план vs факт, пики, тренды, разрезание записи по полуночи |
| `test_quiet.py` | тихий час через полночь, рабочие часы, mute, «следующий момент» |
| `test_schedule_service.py` | создание событий, идемпотентность напоминаний, перенос вхождения |
| `test_drafts.py` | сериализация черновика в FSM, превью |
| `test_i18n_catalog.py` | все `t("…")` из кода есть в каталоге, нет пустых текстов |
| `test_bot_flow.py` | **сквозные сценарии**: онбординг, меню, `/add`, `/today`, настройки, сброс, mute, дедупликация тапов, фоновая отправка напоминаний |

Сквозные тесты не требуют токена и сети: `tests/telegram_fake.py` подменяет сессию
Bot API и записывает все вызовы, а `Dispatcher.feed_update` прогоняет реальный путь
«апдейт → мидлвари → сервис → БД → ответ». Часы тоже подменяются (`build_dispatcher(clock=…)`).

Что тесты уже поймали в процессе разработки (исправлено):
двойной `t()` в онбординге, висячий предлог в названии («Созвон **в**»),
«за час» не распознавалось, невозможность собрать Dispatcher дважды,
неподтверждённые callback-нажатия (кнопка «крутилась»), потеря напоминаний серии
при переносе одного вхождения.

---

## 6. Дальше по этапам

| Этап | Содержание | Что уже готово под него |
|---|---|---|
| 2 | `/start`→таймер, `/stop`, категории кнопками, пауза, автостоп 23:00 | модель `time_logs` с открытым интервалом, reply-кнопка, сервисный слой |
| 3 | отчёты `/week` с PNG, тренды, «💡 Совет» | `services/analytics.py` считает всё, кроме текстов и картинки |
| 4 | пассивные и контекстные опросы, утренний/вечерний дайджест, заполнение пробелов | таблица `polls`, `services/quiet.py`, точки регистрации в `jobs/scheduler.py` |
| 5 | паттерны, Google Calendar, экспорт | `repositories/` как точка расширения, DTO-free структурные типы |

---

## 7. Известные ограничения

* **FSM в памяти процесса** (`MemoryStorage`): перезапуск бота сбрасывает незавершённый
  диалог. Для single-user MVP это нормально; для мультиюзера — замена на Redis в
  `bot/dispatcher.py` (одна строка).
* `build_dispatcher` копирует модульные роутеры (`_fresh_router`), потому что aiogram
  запрещает подключать один Router к двум Dispatcher. Копии нужны тестам и повторной
  сборке в dev-режиме; в проде Dispatcher собирается один раз.
* Графики (`matplotlib`) ещё не подключены — этап 3.
* Логи по умолчанию без фоновой очереди (`LOG_ENQUEUE=false`): бот однопроцессный,
  а `enqueue=True` требует доступа к системным pipe.

### Заметка про окружение разработки

Проект разрабатывался в ограниченной песочнице Windows, где:
* pip не может писать файлы `*.metadata` — зависимости лежат в каталоге `libs/`
  (`PYTHONPATH=src;libs`), а не в venv;
* pytest-установки `0700` недоступны — тесты используют каталог `.pytest-data/` внутри
  проекта вместо системного `tmp_path` (см. `tests/conftest.py`).

На обычной машине или VPS ничего из этого не нужно: достаточно venv и
`pip install -r requirements.txt`. Служебные каталоги (`libs/`, `.deps/`,
`pytest-tmp*/`) добавлены в `.gitignore`.
