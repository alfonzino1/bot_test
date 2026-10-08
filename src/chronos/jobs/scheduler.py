"""Планировщик APScheduler: единая точка регистрации задач.

Расписание задач из ТЗ (раздел 8):

* каждую минуту — напоминания (этап 1, реализовано);
* каждый час в рабочие часы — пассивный опрос (этап 4);
* 8:00 — утренний дайджест (этап 4);
* 20:30 — вечерний дайджест + заполнение пробелов (этап 4);
* 23:00 — автостоп активного таймера (этап 2);
* Пн 9:00 — отчёт за прошлую неделю (этап 3).

Все задачи учитывают тихий час и таймзону: решение о молчании принимает
``chronos.services.quiet``, а не сами джобы.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from chronos.jobs.context import JobContext
from chronos.jobs.reminders import reminder_tick
from chronos.logging_setup import logger

JOB_REMINDERS = "reminders"


def build_scheduler(ctx: JobContext) -> AsyncIOScheduler:
    """Создаёт планировщик с зарегистрированными задачами (этап 1)."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        reminder_tick,
        trigger=IntervalTrigger(minutes=1),
        kwargs={"ctx": ctx},
        id=JOB_REMINDERS,
        name="Напоминания (каждую минуту)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    # ── Этап 2 ───────────────────────────────────────────────────────────────
    # scheduler.add_job(autostop_tick, CronTrigger(hour=23, minute=0), ...)
    # ── Этап 3 ───────────────────────────────────────────────────────────────
    # scheduler.add_job(weekly_report_tick, CronTrigger(day_of_week="mon", hour=9), ...)
    # ── Этап 4 ───────────────────────────────────────────────────────────────
    # scheduler.add_job(passive_poll_tick, IntervalTrigger(hours=1), ...)
    # scheduler.add_job(morning_digest_tick, IntervalTrigger(minutes=1), ...)
    # scheduler.add_job(evening_digest_tick, IntervalTrigger(minutes=1), ...)
    # scheduler.add_job(context_poll_tick, IntervalTrigger(minutes=5), ...)
    logger.debug("Планировщик собран: задач={}", len(scheduler.get_jobs()))
    return scheduler


__all__ = ["JOB_REMINDERS", "build_scheduler"]
