"""Automatic discovery scheduling.

Chosen approach: an APScheduler `BackgroundScheduler` running inside the
same FastAPI process, ticking every `CHECK_INTERVAL_MINUTES` to ask "is a
discovery run due yet?" (per `AppSettings.next_scheduled_run_at`), rather
than scheduling discovery directly at its target frequency. This was
picked over the alternatives for this project's actual scale:

- A dedicated worker process (Celery/RQ + Redis) is real infrastructure
  (a broker, a second deployable, ops surface) for a single-user tool that
  runs at most a few times a day - pure overhead here.
- A bare cron job calling `scripts/run_discovery.py` needs no extra
  infrastructure either, but requires OS-level cron configuration outside
  the app and can't expose "next scheduled run" / "toggle on-off" through
  the API the way an in-process scheduler can.

Trade-off accepted: scheduling state lives only in this process's memory
(a restart re-derives "is it due" from `AppSettings.next_scheduled_run_at`
in Postgres, so nothing is lost - it just isn't a persisted job queue with
its own retry/backoff semantics), and it would not coordinate correctly if
the app ever ran as more than one instance at once (two processes would
each independently decide "it's due" - `DiscoveryService.run()` refusing to
start a second concurrent run limits the damage to "ran twice" rather than
corrupting anything, but it's not a real distributed lock). Neither
constraint matters at this app's current scale; `scripts/run_discovery.py`
(cron-invoked) remains the documented upgrade path if it ever does - the
discovery logic doesn't change, only what triggers it.

For local dev: `uvicorn app.main:app --reload` starts this automatically
(see app/main.py's lifespan) - there's no second process to remember to run.
Default is OFF (`AppSettings.auto_discovery_enabled = False`); the tick
itself is a fast no-op when disabled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.ai.providers.factory import get_llm_provider
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.repositories.app_settings_repository import AppSettingsRepository
from app.services.analysis_orchestrator import CandidateProfileMissingError
from app.services.discovery_service import (
    DiscoveryAlreadyRunningError,
    DiscoveryService,
    NoSearchProfilesError,
)

logger = get_logger(__name__)

SCHEDULER_JOB_ID = "scheduled_discovery_check"
CHECK_INTERVAL_MINUTES = 15

_scheduler: BackgroundScheduler | None = None


def run_scheduled_discovery_if_due() -> None:
    """The actual tick. Public (not `_`-prefixed) so tests can call it
    directly without spinning up a real APScheduler thread."""
    db = SessionLocal()
    try:
        settings_repo = AppSettingsRepository()
        settings = settings_repo.get(db)
        if not settings.auto_discovery_enabled:
            return

        now = datetime.now(UTC)
        next_run_at = settings.next_scheduled_run_at
        if next_run_at is not None:
            # Postgres round-trips DateTime (no tz) columns as naive, so
            # compare on a common (naive) footing rather than assuming
            # both sides carry tzinfo.
            naive_now = now.replace(tzinfo=None)
            naive_next_run_at = next_run_at.replace(tzinfo=None)
            if naive_now < naive_next_run_at:
                return

        try:
            service = DiscoveryService(llm_provider=get_llm_provider())
            service.run(db, triggered_by="scheduled")
            logger.info("scheduled_discovery_completed")
        except DiscoveryAlreadyRunningError:
            logger.warning("scheduled_discovery_skipped_already_running")
        except (CandidateProfileMissingError, NoSearchProfilesError) as exc:
            logger.warning("scheduled_discovery_skipped", reason=str(exc))
        finally:
            settings_repo.set_schedule_timestamps(
                db,
                last_scheduled_run_at=now,
                next_scheduled_run_at=now + timedelta(hours=settings.discovery_frequency_hours),
            )
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_scheduled_discovery_if_due,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id=SCHEDULER_JOB_ID,
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler_started", check_interval_minutes=CHECK_INTERVAL_MINUTES)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler_stopped")
