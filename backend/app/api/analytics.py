from __future__ import annotations

import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Application,
    Intervention,
    JobListing,
    RunBatch,
    User,
    utcnow,
)

router = APIRouter()

SUBMITTED = ("submitted", "submitted_unconfirmed")
RESPONSE_OUTCOMES = ("recruiter_reply", "interview", "offer")


class MetricCards(BaseModel):
    found_today: int
    applied_this_week: int
    responses: int
    interviews: int
    offers: int
    pending_interventions: int
    total_listings: int
    total_applications: int
    active_runs: int


class TimePoint(BaseModel):
    date: str
    found: int
    applied: int


class Breakdown(BaseModel):
    key: str
    total: int
    applied: int
    responses: int


class FunnelStage(BaseModel):
    stage: str
    count: int


class Dashboard(BaseModel):
    cards: MetricCards
    over_time: list[TimePoint]
    by_source: list[Breakdown]
    response_rate_by_source: list[Breakdown]
    funnel: list[FunnelStage]


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


@router.get("", response_model=Dashboard)
def dashboard(
    days: int = Query(default=30, ge=7, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dashboard:
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - dt.timedelta(days=7)
    window_start = now - dt.timedelta(days=days)

    listings = list(db.scalars(select(JobListing).where(JobListing.user_id == user.id)))
    apps = list(db.scalars(select(Application).where(Application.user_id == user.id)))

    found_today = sum(1 for li in listings if (_aware(li.fetched_at) or now) >= today_start)
    applied_week = sum(
        1 for a in apps if a.status in SUBMITTED and (_aware(a.submitted_at) or now) >= week_start
    )
    responses = sum(1 for a in apps if a.outcome in RESPONSE_OUTCOMES)
    interviews = sum(1 for a in apps if a.outcome in ("interview", "offer"))
    offers = sum(1 for a in apps if a.outcome == "offer")

    pending = int(
        db.scalar(
            select(func.count(Intervention.id)).where(
                Intervention.user_id == user.id, Intervention.status == "open"
            )
        )
        or 0
    )
    active_runs = int(
        db.scalar(
            select(func.count(RunBatch.id)).where(
                RunBatch.user_id == user.id, RunBatch.status == "running"
            )
        )
        or 0
    )

    cards = MetricCards(
        found_today=found_today,
        applied_this_week=applied_week,
        responses=responses,
        interviews=interviews,
        offers=offers,
        pending_interventions=pending,
        total_listings=len(listings),
        total_applications=len(apps),
        active_runs=active_runs,
    )

    # Applications-over-time / listings-over-time.
    found_by_day: dict[str, int] = defaultdict(int)
    applied_by_day: dict[str, int] = defaultdict(int)
    for li in listings:
        fetched = _aware(li.fetched_at)
        if fetched and fetched >= window_start:
            found_by_day[fetched.date().isoformat()] += 1
    for a in apps:
        submitted = _aware(a.submitted_at)
        if a.status in SUBMITTED and submitted and submitted >= window_start:
            applied_by_day[submitted.date().isoformat()] += 1
    over_time = []
    for offset in range(days, -1, -1):
        day = (now - dt.timedelta(days=offset)).date().isoformat()
        over_time.append(
            TimePoint(date=day, found=found_by_day.get(day, 0), applied=applied_by_day.get(day, 0))
        )

    # Per-source breakdown.
    listing_source = {li.id: li.source for li in listings}
    by_source_totals: dict[str, int] = defaultdict(int)
    for li in listings:
        by_source_totals[li.source] += 1
    by_source_applied: dict[str, int] = defaultdict(int)
    by_source_responses: dict[str, int] = defaultdict(int)
    for a in apps:
        source = listing_source.get(a.listing_id, "unknown")
        if a.status in SUBMITTED:
            by_source_applied[source] += 1
            if a.outcome in RESPONSE_OUTCOMES:
                by_source_responses[source] += 1
    by_source = [
        Breakdown(
            key=source,
            total=total,
            applied=by_source_applied.get(source, 0),
            responses=by_source_responses.get(source, 0),
        )
        for source, total in sorted(by_source_totals.items(), key=lambda kv: -kv[1])
    ]
    response_rate = [
        b for b in sorted(by_source, key=lambda b: -(b.responses / b.applied if b.applied else 0))
        if b.applied
    ]

    # Funnel.
    funnel = [
        FunnelStage(stage="Found", count=len(listings)),
        FunnelStage(stage="Applied", count=sum(1 for a in apps if a.status in SUBMITTED)),
        FunnelStage(
            stage="Response",
            count=sum(1 for a in apps if a.outcome in RESPONSE_OUTCOMES),
        ),
        FunnelStage(stage="Interview", count=sum(1 for a in apps if a.outcome in ("interview", "offer"))),
        FunnelStage(stage="Offer", count=offers),
    ]

    return Dashboard(
        cards=cards,
        over_time=over_time,
        by_source=by_source,
        response_rate_by_source=response_rate,
        funnel=funnel,
    )
