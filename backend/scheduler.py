"""
Runs two automated jobs so the ranked list fills in and stays current without
any manual button-clicking:

1. Price/technicals refresh (refresh_service.refresh_all) — every
   REFRESH_INTERVAL_MINUTES, but only during NSE market hours on weekdays.
2. Fundamentals refresh (refresh_service.refresh_fundamentals_all) — once a
   day, since fundamentals change far slower than prices. Also runs once
   shortly after startup so a fresh deploy doesn't sit empty for a day.
"""
import datetime as dt
import os
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

import refresh_service

logger = logging.getLogger("scheduler")

REFRESH_INTERVAL_MINUTES = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))
FUNDAMENTALS_INTERVAL_HOURS = int(os.environ.get("FUNDAMENTALS_INTERVAL_HOURS", "24"))
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_scheduler = None


def _is_market_hours_ist(now: dt.datetime) -> bool:
    now_ist = now.astimezone(IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    open_t = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now_ist <= close_t


def _price_job():
    now = dt.datetime.now(dt.timezone.utc)
    if not _is_market_hours_ist(now):
        logger.info("Outside market hours — skipping scheduled price refresh")
        return
    logger.info("Running scheduled price refresh...")
    result = refresh_service.refresh_all()
    logger.info("Scheduled price refresh done: %s", result)


def _fundamentals_job():
    logger.info("Running scheduled fundamentals refresh...")
    result = refresh_service.refresh_fundamentals_all()
    logger.info("Scheduled fundamentals refresh done: %s", result)


def start():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_price_job, IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
                        id="refresh_prices", replace_existing=True)
    _scheduler.add_job(_fundamentals_job, IntervalTrigger(hours=FUNDAMENTALS_INTERVAL_HOURS),
                        id="refresh_fundamentals", replace_existing=True)
    # Run fundamentals once ~2 minutes after startup too, so a fresh deploy
    # (or a bulk-added universe) doesn't sit with empty fundamentals for a
    # full day waiting for the first scheduled run.
    _scheduler.add_job(_fundamentals_job,
                        DateTrigger(run_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)),
                        id="fundamentals_initial_run", replace_existing=True)
    _scheduler.start()
    logger.info("Scheduler started — prices every %s min (market hours), fundamentals every %s hours",
                REFRESH_INTERVAL_MINUTES, FUNDAMENTALS_INTERVAL_HOURS)
    return _scheduler


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
