"""arq worker: the Playwright queue runner and scheduled saved-searches.

Every ~15s it parks lapsed interventions and processes a slice of pending
Playwright work per active user. Scheduled search targets run on their own
cadence. Resilient: each user's batch is isolated, failures are logged and
the loop continues, and applications that error are re-queueable from the UI.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import distinct, select

from app.config import get_settings
from app.db import get_sessionmaker
from app.logging_conf import configure_logging, get_logger
from app.models import Application, RunBatch, SearchTarget, User, utcnow

__all__ = ["WorkerSettings", "process_queue", "run_scheduled_searches"]

log = get_logger(__name__)


async def process_queue(ctx: dict) -> int:
    """Run one tick of the Playwright queue for every user with active work."""
    from app.executor.runner import park_expired_interventions, run_pending_for_user

    session_local = get_sessionmaker()
    db = session_local()
    try:
        park_expired_interventions(db)
        db.commit()
        running = select(distinct(RunBatch.user_id)).where(RunBatch.status == "running")
        user_ids = list(
            db.scalars(
                select(distinct(Application.user_id)).where(
                    Application.status.in_(["queued", "needs_human"]),
                    Application.run_batch_id.in_(running),
                )
            )
        )
        # Only drive users whose executor preference includes playwright or is
        # unassigned; the extension drives its own via HTTP long-poll.
        db.commit()
    finally:
        db.close()

    total = 0
    for user_id in user_ids:
        try:
            total += run_pending_for_user(user_id, max_jobs=3)
        except Exception:
            log.exception("worker.user_failed", user_id=user_id)
    _finalize_runs()
    if total:
        log.info("worker.tick", processed=total)
    return total


def _finalize_runs() -> None:
    """Mark runs completed when they have no remaining active work."""
    session_local = get_sessionmaker()
    db = session_local()
    try:
        batches = db.scalars(select(RunBatch).where(RunBatch.status == "running"))
        for batch in batches:
            remaining = db.scalar(
                select(Application.id).where(
                    Application.run_batch_id == batch.id,
                    Application.status.in_(["queued", "filling", "submitting"]),
                )
            )
            # needs_human that is parked (waiting) does not keep a run "running"
            # forever; but open needs_human still counts as in-flight.
            open_human = db.scalar(
                select(Application.id).where(
                    Application.run_batch_id == batch.id,
                    Application.status == "needs_human",
                    Application.parked_at.is_(None),
                )
            )
            if remaining is None and open_human is None:
                batch.status = "completed"
                batch.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


async def run_scheduled_searches(ctx: dict) -> int:
    """Run saved searches whose cadence is due."""
    from app.services.search_service import SearchRun, execute_search
    from app.sources.base import SearchQuery

    session_local = get_sessionmaker()
    db = session_local()
    ran = 0
    try:
        now = utcnow()
        targets = db.scalars(
            select(SearchTarget).where(SearchTarget.schedule_minutes.is_not(None))
        )
        due = []
        for target in targets:
            interval = target.schedule_minutes
            if interval is None:
                continue
            last = target.last_run_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=dt.UTC)
            if last is None or (now - last).total_seconds() >= interval * 60:
                due.append(target)
        for target in due:
            user = db.get(User, target.user_id)
            if user is None:
                continue
            target.last_run_at = now
            db.commit()
            run = SearchRun(id=f"sched-{target.id}", user_id=user.id)
            query = SearchQuery(
                terms=target.title_terms,
                location=target.location,
                remote=target.remote,
                salary_floor=target.salary_floor,
                education_level=target.education_level,
                posted_within_days=target.posted_within_days,
            )
            try:
                # The target's terms are job titles, so gate on them: only
                # those roles and their recognised variations are kept.
                execute_search(db, user, query, target.sources, run, role_titles=target.title_terms)
                db.commit()
                ran += 1
            except Exception:
                db.rollback()
                log.exception("worker.scheduled_search_failed", target_id=target.id)
    finally:
        db.close()
    return ran


async def _on_startup(ctx: dict) -> None:
    configure_logging()
    log.info("worker.started")


def _build_cron_jobs() -> list:
    from arq import cron

    return [
        # The Playwright queue runner ticks every 15s.
        cron(process_queue, second={0, 15, 30, 45}, run_at_startup=True),
        # Scheduled saved-searches are checked every 5 minutes.
        cron(run_scheduled_searches, minute=set(range(0, 60, 5))),
    ]


def _redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """arq reads this class at `app.workers.main.WorkerSettings`."""

    functions = [process_queue, run_scheduled_searches]
    redis_settings = _redis_settings()
    cron_jobs = _build_cron_jobs()
    on_startup = _on_startup
    max_jobs = 4
