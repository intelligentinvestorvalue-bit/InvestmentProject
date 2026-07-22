"""Background scheduled sync jobs."""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _run_us_sync(app: Flask) -> None:
    with app.app_context():
        from app.services.sec_form4 import sync_us_insider_feed

        days = int(app.config.get("US_SYNC_DAYS", 7))
        max_filings = int(app.config.get("US_SYNC_MAX_FILINGS", app.config.get("SYNC_MAX_FILINGS", 25)))
        try:
            result = sync_us_insider_feed(
                days=days,
                max_filings=max_filings,
                trigger="scheduled",
                mode="recent",
            )
            logger.info("Scheduled US sync completed: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled US sync failed")


def _run_in_sync(app: Flask) -> None:
    with app.app_context():
        from app.services.india_provider import sync_india_insider_feed

        days = int(app.config.get("IN_SYNC_DAYS", 120))
        try:
            result = sync_india_insider_feed(days=days, trigger="scheduled", include_extra=True)
            logger.info("Scheduled India sync completed: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled India sync failed")


def _run_uoa_poll(app: Flask) -> None:
    """Near-real-time-ish delayed scan over watchlist + a capped liquid set."""
    with app.app_context():
        if not app.config.get("UOA_ENABLED", True):
            return
        from app.services.uoa_scanner import run_uoa_scan

        try:
            result = run_uoa_scan(
                include_watchlist=True,
                include_liquid=True,
                trigger="poll",
                max_tickers=int(app.config.get("UOA_POLL_MAX_TICKERS", 25)),
            )
            logger.info("UOA poll completed: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("UOA poll failed")


def _run_uoa_eod(app: Flask) -> None:
    """Broader end-of-day / delayed full-ish scan."""
    with app.app_context():
        if not app.config.get("UOA_ENABLED", True):
            return
        from app.services.uoa_scanner import run_uoa_scan

        try:
            result = run_uoa_scan(
                include_watchlist=True,
                include_liquid=True,
                trigger="eod",
                max_tickers=int(app.config.get("UOA_EOD_MAX_TICKERS", 80)),
            )
            logger.info("UOA EOD completed: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("UOA EOD failed")


def init_scheduler(app: Flask) -> Optional[BackgroundScheduler]:
    """Start APScheduler once per process when enabled."""
    global _scheduler
    if not app.config.get("SCHEDULER_ENABLED", True):
        logger.info("Scheduler disabled via config")
        return None

    # Avoid double-start with Flask debug reloader.
    import os

    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    if _scheduler and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(daemon=True)
    us_minutes = int(app.config.get("US_SYNC_INTERVAL_MINUTES", 60))
    in_minutes = int(app.config.get("IN_SYNC_INTERVAL_MINUTES", 90))
    uoa_poll_minutes = int(app.config.get("UOA_POLL_INTERVAL_MINUTES", 20))
    uoa_eod_hour = int(app.config.get("UOA_EOD_HOUR_UTC", 21))

    scheduler.add_job(
        _run_us_sync,
        "interval",
        minutes=max(us_minutes, 15),
        args=[app],
        id="us_insider_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_in_sync,
        "interval",
        minutes=max(in_minutes, 30),
        args=[app],
        id="in_insider_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if app.config.get("UOA_ENABLED", True):
        scheduler.add_job(
            _run_uoa_poll,
            "interval",
            minutes=max(uoa_poll_minutes, 10),
            args=[app],
            id="uoa_poll",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            _run_uoa_eod,
            "cron",
            hour=max(0, min(uoa_eod_hour, 23)),
            minute=10,
            args=[app],
            id="uoa_eod",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started (US %sm, IN %sm, UOA poll %sm, UOA EOD %s:10 UTC)",
        max(us_minutes, 15),
        max(in_minutes, 30),
        max(uoa_poll_minutes, 10),
        max(0, min(uoa_eod_hour, 23)),
    )
    return scheduler


def scheduler_status() -> dict:
    if not _scheduler:
        return {"enabled": False, "running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )
    return {"enabled": True, "running": bool(_scheduler.running), "jobs": jobs}
