"""
Runs refresh_service.refresh_all() automatically on a timer, but only during
roughly NSE market hours on weekdays — no point burning API calls (or getting
rate-limited) refreshing prices at 2am when nothing has changed.
"""
import datetime as dt
import os
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import refresh_service

logger = logging.getLogger("scheduler")

REFRESH_INTERVAL_MINUTES = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_scheduler = None


def _is_market_hours_ist(now: dt.datetime) -> bool:
    now_ist = now.astimezone(IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    open_t = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now_ist <= close_t


def _job():
    now = dt.datetime.now(dt.timezone.utc)
    if not _is_market_hours_ist(now):
        logger.info("Outside market hours — skipping scheduled refresh")
        return
    logger.info("Running scheduled refresh...")
    result = refresh_service.refresh_all()
    logger.info("Scheduled refresh done: %s", result)


def start():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job, IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES), id="refresh", replace_existing=True)
    _scheduler.start()
    logger.info("Scheduler started — refreshing every %s minutes during market hours", REFRESH_INTERVAL_MINUTES)
    return _scheduler


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
