"""Server-side application-throughput ceilings.

Default 15/hour and 50/day (configurable), enforced in the queue runner and
at every submission entry point — the extension cannot bypass them because
the check runs on the server before any job is handed out and again before
any transition into `submitting`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application, utcnow


@dataclass
class PacingDecision:
    allowed: bool
    reason: str | None = None
    retry_at: dt.datetime | None = None
    submitted_last_hour: int = 0
    submitted_last_day: int = 0


def _count_since(db: Session, user_id: int, since: dt.datetime) -> int:
    return int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.user_id == user_id,
                Application.submitted_at.is_not(None),
                Application.submitted_at >= since,
            )
        )
        or 0
    )


def check_submission_allowance(db: Session, user_id: int) -> PacingDecision:
    settings = get_settings()
    now = utcnow()
    hour_count = _count_since(db, user_id, now - dt.timedelta(hours=1))
    day_count = _count_since(db, user_id, now - dt.timedelta(days=1))
    if day_count >= settings.max_applications_per_day:
        return PacingDecision(
            allowed=False,
            reason=f"Daily ceiling reached ({settings.max_applications_per_day}/day)",
            retry_at=now + dt.timedelta(hours=1),
            submitted_last_hour=hour_count,
            submitted_last_day=day_count,
        )
    if hour_count >= settings.max_applications_per_hour:
        return PacingDecision(
            allowed=False,
            reason=f"Hourly ceiling reached ({settings.max_applications_per_hour}/hour)",
            retry_at=now + dt.timedelta(minutes=10),
            submitted_last_hour=hour_count,
            submitted_last_day=day_count,
        )
    return PacingDecision(
        allowed=True, submitted_last_hour=hour_count, submitted_last_day=day_count
    )
