from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.executor.states import InvalidTransitionError, record_event, transition
from app.models import (
    OUTCOMES,
    Application,
    ApplicationEvent,
    Intervention,
    JobListing,
    User,
    utcnow,
)
from app.schemas.auth import OkResponse

router = APIRouter()


class ApplicationOut(BaseModel):
    id: int
    listing_id: int
    run_batch_id: int | None
    status: str
    mode: str
    executor: str | None
    humanize: bool | None
    needs_human_reason: str | None
    parked_at: dt.datetime | None
    submitted_at: dt.datetime | None
    error: str | None
    outcome: str
    created_at: dt.datetime
    updated_at: dt.datetime
    # joined listing display fields
    title: str | None = None
    company: str | None = None
    listing_url: str | None = None
    open_interventions: int = 0

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    type: str
    payload: dict[str, Any]
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class InterventionBrief(BaseModel):
    id: int
    kind: str
    status: str
    question: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ApplicationDetail(ApplicationOut):
    field_snapshot: dict[str, Any] | None
    confirmation_screenshot_url: str | None = None
    events: list[EventOut] = []
    interventions: list[InterventionBrief] = []


def _decorate(db: Session, rows: list[Application]) -> list[ApplicationOut]:
    listing_ids = {r.listing_id for r in rows}
    listings = {
        li.id: li
        for li in db.scalars(select(JobListing).where(JobListing.id.in_(listing_ids)))
    }
    open_counts: dict[int, int] = {}
    for iv in db.scalars(
        select(Intervention).where(
            Intervention.application_id.in_([r.id for r in rows]),
            Intervention.status == "open",
        )
    ):
        open_counts[iv.application_id] = open_counts.get(iv.application_id, 0) + 1
    out = []
    for row in rows:
        item = ApplicationOut.model_validate(row)
        listing = listings.get(row.listing_id)
        if listing:
            item.title = listing.title
            item.company = listing.company
            item.listing_url = listing.canonical_url
        item.open_interventions = open_counts.get(row.id, 0)
        out.append(item)
    return out


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    limit: int = Query(default=200, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicationOut]:
    stmt = select(Application).where(Application.user_id == user.id)
    if status_filter:
        stmt = stmt.where(Application.status.in_(status_filter.split(",")))
    if q:
        needle = f"%{q.lower()}%"
        listing_ids = select(JobListing.id).where(
            JobListing.user_id == user.id,
            or_(JobListing.title.ilike(needle), JobListing.company.ilike(needle)),
        )
        stmt = stmt.where(Application.listing_id.in_(listing_ids))
    rows = list(db.scalars(stmt.order_by(Application.updated_at.desc()).limit(limit)))
    return _decorate(db, rows)


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ApplicationDetail:
    row = db.get(Application, application_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    base = _decorate(db, [row])[0]
    detail = ApplicationDetail(**base.model_dump(), field_snapshot=row.field_snapshot)
    if row.confirmation_screenshot_path:
        detail.confirmation_screenshot_url = f"/api/applications/{row.id}/screenshot"
    detail.events = [
        EventOut.model_validate(e)
        for e in db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == row.id)
            .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
        )
    ]
    detail.interventions = [
        InterventionBrief.model_validate(i)
        for i in db.scalars(
            select(Intervention)
            .where(Intervention.application_id == row.id)
            .order_by(Intervention.id)
        )
    ]
    return detail


@router.get("/{application_id}/screenshot")
def confirmation_screenshot(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from fastapi.responses import FileResponse

    from app.services.storage import resolve_user_path

    row = db.get(Application, application_id)
    if row is None or row.user_id != user.id or not row.confirmation_screenshot_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        path = resolve_user_path(user.id, row.confirmation_screenshot_path)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Path scoping violation") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot missing")
    return FileResponse(path, media_type="image/png")


class OutcomeRequest(BaseModel):
    outcome: str


@router.post("/{application_id}/outcome", response_model=OkResponse)
def set_outcome(
    application_id: int,
    payload: OutcomeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    if payload.outcome not in OUTCOMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"outcome must be one of {OUTCOMES}")
    row = db.get(Application, application_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.outcome = payload.outcome
    row.outcome_updated_at = utcnow()
    record_event(db, row, "outcome.updated", {"outcome": payload.outcome})
    return OkResponse()


@router.post("/{application_id}/requeue", response_model=OkResponse)
def requeue(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(Application, application_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        transition(db, row, "queued", reason="requeued by user", actor="user")
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return OkResponse()


@router.post("/{application_id}/skip", response_model=OkResponse)
def skip(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(Application, application_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        transition(db, row, "skipped", reason="skipped by user", actor="user")
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return OkResponse()
