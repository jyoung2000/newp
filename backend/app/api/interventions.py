from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Application, Intervention, JobListing, User
from app.schemas.auth import OkResponse
from app.services.intervention_service import answer_intervention

router = APIRouter()


class InterventionOut(BaseModel):
    id: int
    application_id: int
    kind: str
    status: str
    question: str | None
    field_meta: dict[str, Any]
    answer: Any | None
    saved_to_kb: bool
    resolved_by: str | None
    resolved_at: dt.datetime | None
    created_at: dt.datetime
    screenshot_url: str | None = None
    # context for answering from a phone without scrolling back
    listing_title: str | None = None
    listing_company: str | None = None
    application_status: str | None = None

    model_config = {"from_attributes": True}


def _decorate(db: Session, rows: list[Intervention]) -> list[InterventionOut]:
    app_ids = {r.application_id for r in rows}
    apps = {a.id: a for a in db.scalars(select(Application).where(Application.id.in_(app_ids)))}
    listings = {
        li.id: li
        for li in db.scalars(
            select(JobListing).where(
                JobListing.id.in_({a.listing_id for a in apps.values()})
            )
        )
    }
    out = []
    for row in rows:
        item = InterventionOut.model_validate(row)
        if row.screenshot_path:
            item.screenshot_url = f"/api/interventions/{row.id}/screenshot"
        app = apps.get(row.application_id)
        if app:
            item.application_status = app.status
            listing = listings.get(app.listing_id)
            if listing:
                item.listing_title = listing.title
                item.listing_company = listing.company
        out.append(item)
    return out


@router.get("", response_model=list[InterventionOut])
def list_interventions(
    status_filter: str | None = Query(default="open", alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InterventionOut]:
    stmt = select(Intervention).where(Intervention.user_id == user.id)
    if status_filter and status_filter != "all":
        stmt = stmt.where(Intervention.status.in_(status_filter.split(",")))
    rows = list(db.scalars(stmt.order_by(Intervention.id.desc()).limit(200)))
    return _decorate(db, rows)


@router.get("/{intervention_id}", response_model=InterventionOut)
def get_intervention(
    intervention_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InterventionOut:
    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _decorate(db, [row])[0]


@router.get("/{intervention_id}/screenshot")
def intervention_screenshot(
    intervention_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from fastapi.responses import FileResponse

    from app.services.storage import resolve_user_path

    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id or not row.screenshot_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        path = resolve_user_path(user.id, row.screenshot_path)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Path scoping violation") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot missing")
    return FileResponse(path, media_type="image/png")


class AnswerRequest(BaseModel):
    answer: Any = None
    save_to_kb: bool = True
    question_key: str | None = None  # user-editable normalized key
    skip: bool = False


@router.post("/{intervention_id}/answer", response_model=InterventionOut)
def answer(
    intervention_id: int,
    payload: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterventionOut:
    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Intervention already {row.status}")
    if row.kind == "challenge":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Challenges are not answered in JobPilot — solve it in the page, then mark it done",
        )
    if not payload.skip and payload.answer in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide an answer or skip")
    answer_intervention(
        db,
        user,
        row,
        payload.answer,
        save_to_kb=payload.save_to_kb,
        question_key_override=payload.question_key,
        skip=payload.skip,
    )
    return _decorate(db, [row])[0]


@router.post("/{intervention_id}/challenge-done", response_model=InterventionOut)
def challenge_done(
    intervention_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InterventionOut:
    """The human reports they personally completed the challenge. The
    executor still re-verifies the challenge element is gone before any
    input resumes."""
    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if row.kind != "challenge":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a challenge intervention")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Intervention already {row.status}")
    answer_intervention(db, user, row, {"human_solved": True}, save_to_kb=False)
    return _decorate(db, [row])[0]


@router.post("/{intervention_id}/approve-review", response_model=InterventionOut)
def approve_review(
    intervention_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InterventionOut:
    """Approve a review-mode application for submission."""
    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if row.kind != "review":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a review intervention")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Intervention already {row.status}")
    answer_intervention(db, user, row, {"approved": True}, save_to_kb=False)
    return _decorate(db, [row])[0]


@router.post("/{intervention_id}/cancel", response_model=OkResponse)
def cancel(
    intervention_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(Intervention, intervention_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Intervention already {row.status}")
    row.status = "cancelled"
    return OkResponse()
