import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import AUTO_REFRESH_MINUTES
from app.services.monitor import check_all_servers


logger = logging.getLogger(__name__)

NAIROBI_TIMEZONE = ZoneInfo("Africa/Nairobi")

scheduler = BackgroundScheduler(
    timezone=NAIROBI_TIMEZONE,
)


def scheduled_monitoring_check(
    servers: list[dict[str, Any]],
) -> None:
    """
    Run all API and system checks from the background scheduler.
    """

    started_at = datetime.now(NAIROBI_TIMEZONE)

    logger.info(
        "Starting scheduled monitoring check at %s",
        started_at.isoformat(timespec="seconds"),
    )

    try:
        results = check_all_servers(servers)

        logger.info(
            "Scheduled monitoring check completed for %d servers",
            len(results),
        )

    except Exception:
        logger.exception(
            "Scheduled monitoring check failed"
        )


def start_scheduler(
    servers: list[dict[str, Any]],
) -> None:
    """
    Start the background scheduler if it is not already running.
    """

    if scheduler.running:
        logger.warning(
            "Monitoring scheduler is already running"
        )
        return

    scheduler.add_job(
        scheduled_monitoring_check,
        trigger="interval",
        minutes=AUTO_REFRESH_MINUTES,
        args=[servers],
        id="monitor-all-servers",
        name="Monitor all IMAL servers",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()

    logger.info(
        "Monitoring scheduler started with a %d-minute interval",
        AUTO_REFRESH_MINUTES,
    )


def stop_scheduler() -> None:
    """
    Stop the scheduler gracefully during application shutdown.
    """

    if scheduler.running:
        scheduler.shutdown(
            wait=False,
        )

        logger.info(
            "Monitoring scheduler stopped"
        )


def get_scheduler_status() -> dict[str, Any]:
    """
    Return information about the monitoring schedule.
    """

    job = scheduler.get_job(
        "monitor-all-servers"
    )

    return {
        "running": scheduler.running,
        "interval_minutes": AUTO_REFRESH_MINUTES,
        "next_run_at": (
            job.next_run_time.isoformat(
                timespec="seconds"
            )
            if job and job.next_run_time
            else None
        ),
    }
