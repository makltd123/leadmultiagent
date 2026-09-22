import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _weekly_scout_job() -> None:
    logger.info("Scheduler: запуск еженедельного Scout")
    try:
        from userbot import app as userbot_app
        import agents.scout as scout
        await scout.run(userbot_app)
    except Exception:
        logger.exception("Scheduler: ошибка Scout")


async def _weekly_digest_job() -> None:
    logger.info("Scheduler: запуск еженедельного дайджеста")
    try:
        from config import ADMIN_ID
        from bot import build_application
        import agents.analyst as analyst
        app = build_application()
        async with app:
            await analyst.run_weekly_digest(app.bot, ADMIN_ID)
    except Exception:
        logger.exception("Scheduler: ошибка Analyst")


def build_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _weekly_scout_job,
        trigger="cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        id="weekly_scout",
    )
    _scheduler.add_job(
        _weekly_digest_job,
        trigger="cron",
        day_of_week="sun",
        hour=10,
        minute=0,
        id="weekly_digest",
    )
    return _scheduler


async def run_scheduler() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Scheduler запущен (scout пн 03:00, дайджест вс 10:00)")
    import asyncio
    await asyncio.Event().wait()
