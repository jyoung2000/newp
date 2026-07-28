from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.executor.states import InvalidTransitionError, record_event, transition
from app.models import Application, JobListing, RunBatch, User, utcnow
from app.schemas.auth import UserSettings
from app.services.pacing import check_submission_allowance
from app.ws import publish_sync

router = APIRouter()


class RunCreate(BaseModel):
    listing_ids: list[int] = Field(min_length=1)
    mode: str = Field(pattern="^(auto|review|draft)$")
    executor: str | None = Field(default=None, pattern="^(extension|playwright)$")
    humanize: bool | None = None  # None = user default
    resume_file_id: int | None = None


class RunOut(BaseModel):
    id: int
    mode: str
    executor: str | None
    humanize: bool | None
    status: str
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    total: int = 0
    queued: int = 0
    filling: int = 0
    needs_human: int = 0
    submitted: int = 0
    drafted: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: int = 0

    model_config = {"from_attributes": True}


class RunCreated(BaseModel):
    run: RunOut
    created_applications: int
    already_applied: list[int]
    pacing_note: str | None = None


def _run_out(db: Session, batch: RunBatch) -> RunOut:
    out = RunOut.model_validate(batch)
    apps = list(db.scalars(select(Application).where(Application.run_batch_id == batch.id)))
    out.total = len(apps)
    for app in apps:
        if app.status == "queued":
            out.queued += 1
        elif app.status == "filling":
            out.filling += 1
        elif app.status == "needs_human":
            out.needs_human += 1
        elif app.status in ("submitted", "submitted_unconfirmed"):
            out.submitted += 1
        elif app.status == "drafted":
            out.drafted += 1
        elif app.status == "failed":
            out.failed += 1
        elif app.status == "skipped":
            out.skipped += 1
        elif app.status == "stopped":
            out.stopped += 1
    return out


@router.post("", response_model=RunCreated, status_code=201)
def create_run(
    payload: RunCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RunCreated:
    settings = UserSettings.model_validate({**UserSettings().model_dump(), **(user.settings or {})})
    humanize = payload.humanize if payload.humanize is not None else settings.humanize_default
    executor = payload.executor or (
        None if settings.executor_default == "auto" else settings.executor_default
    )
    batch = RunBatch(
        user_id=user.id,
        mode=payload.mode,
        executor=executor,
        humanize=humanize,
        status="running",
        started_at=utcnow(),
        settings_snapshot={
            "humanize": humanize,
            "executor": executor,
            "mode": payload.mode,
            "resume_file_id": payload.resume_file_id,
        },
    )
    db.add(batch)
    db.flush()

    created = 0
    already: list[int] = []
    for listing_id in dict.fromkeys(payload.listing_ids):
        listing = db.get(JobListing, listing_id)
        if listing is None or listing.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Listing {listing_id} not found")
        existing = db.scalar(
            select(Application).where(
                Application.user_id == user.id, Application.listing_id == listing_id
            )
        )
        if existing is not None:
            # One application per user per posting, ever.
            already.append(listing_id)
            continue
        app = Application(
            user_id=user.id,
            listing_id=listing_id,
            run_batch_id=batch.id,
            status="draft",
            mode=payload.mode,
            executor=executor,
            humanize=humanize,
            resume_file_id=payload.resume_file_id,
        )
        db.add(app)
        db.flush()
        record_event(db, app, "created", {"mode": payload.mode})
        transition(db, app, "queued", reason="added to run", actor="user")
        created += 1

    pacing = check_submission_allowance(db, user.id)
    pacing_note = None if pacing.allowed else pacing.reason
    publish_sync(user.id, {"type": "run.created", "run_id": batch.id, "also_ext": True})
    return RunCreated(
        run=_run_out(db, batch),
        created_applications=created,
        already_applied=already,
        pacing_note=pacing_note,
    )


@router.get("", response_model=list[RunOut])
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[RunOut]:
    batches = db.scalars(
        select(RunBatch).where(RunBatch.user_id == user.id).order_by(RunBatch.id.desc()).limit(50)
    )
    return [_run_out(db, b) for b in batches]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RunOut:
    batch = db.get(RunBatch, run_id)
    if batch is None or batch.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _run_out(db, batch)


def _get_batch(db: Session, user: User, run_id: int) -> RunBatch:
    batch = db.get(RunBatch, run_id)
    if batch is None or batch.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return batch


@router.post("/{run_id}/pause", response_model=RunOut)
def pause_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RunOut:
    batch = _get_batch(db, user, run_id)
    if batch.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is {batch.status}")
    batch.status = "paused"
    publish_sync(user.id, {"type": "run.paused", "run_id": batch.id, "also_ext": True})
    return _run_out(db, batch)


@router.post("/{run_id}/resume", response_model=RunOut)
def resume_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RunOut:
    batch = _get_batch(db, user, run_id)
    if batch.status != "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is {batch.status}")
    batch.status = "running"
    publish_sync(user.id, {"type": "run.resumed", "run_id": batch.id, "also_ext": True})
    return _run_out(db, batch)


@router.post("/{run_id}/stop", response_model=RunOut)
def stop_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RunOut:
    """Stop a run. Queued applications stop immediately; in-flight fills see
    the stop flag at their next checkpoint and abort without submitting —
    a stopped run leaves no half-submitted forms."""
    batch = _get_batch(db, user, run_id)
    if batch.status in ("stopped", "completed"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is {batch.status}")
    batch.status = "stopped"
    batch.finished_at = utcnow()
    for app in db.scalars(
        select(Application).where(
            Application.run_batch_id == batch.id, Application.status == "queued"
        )
    ):
        try:
            transition(db, app, "stopped", reason="run stopped", actor="user")
        except InvalidTransitionError:  # pragma: no cover - race
            pass
    publish_sync(user.id, {"type": "run.stopped", "run_id": batch.id, "also_ext": True})
    return _run_out(db, batch)
