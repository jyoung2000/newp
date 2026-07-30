"""The roles a user wants, in the user's own language.

A "role" is a job title someone is looking for. Underneath, each one is a
SearchTarget — the scheduled-discovery machinery already reads those every five
minutes (workers/main.run_scheduled_searches), so a role saved here starts
finding jobs without anything else being wired up.

What this module adds over the raw target CRUD is the part a person cares
about: a role carries the **variations** that count as the same job, they are
visible before saving, and they are editable. services/titles.py proposes them;
the user has the last word. That matters because the proposal comes from a
curated vocabulary that cannot know every industry — showing it and letting it
be corrected is the difference between a helpful default and a wrong guess.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.logging_conf import get_logger
from app.models import JobListing, SearchTarget, User
from app.schemas.auth import OkResponse
from app.services import titles

log = get_logger(__name__)
router = APIRouter()

# Every three hours. Frequent enough that a new posting surfaces the same day,
# gentle enough to stay well inside the politeness budget the sources are
# held to.
DEFAULT_SCHEDULE_MINUTES = 180


class RolePreview(BaseModel):
    title: str
    # What JobPilot would accept as the same job. Shown before saving so the
    # user can see what they are agreeing to.
    variations: list[str]
    # True when the title is one the vocabulary recognises. False means matching
    # falls back to word overlap, which works but is looser — worth saying.
    recognised: bool


class RoleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Omitted on create: the proposed variations are used. Sent explicitly when
    # the user has edited them.
    variations: list[str] | None = None
    location: str | None = Field(default=None, max_length=200)
    remote: bool | None = None
    salary_floor: int | None = Field(default=None, ge=0)
    schedule_minutes: int | None = Field(default=DEFAULT_SCHEDULE_MINUTES, ge=30)


class RoleOut(BaseModel):
    id: int
    title: str
    variations: list[str]
    location: str | None = None
    remote: bool | None = None
    salary_floor: int | None = None
    schedule_minutes: int | None = None
    last_run_at: dt.datetime | None = None
    # How many listings arrived for this role, so the UI can show it working.
    listings_found: int = 0


def _terms(title: str, variations: list[str] | None) -> list[str]:
    """The search terms for a role: the title first, then its variations.

    The title always leads and is always present — a user's own wording is not
    something to drop because a proposal didn't include it.
    """
    proposed = variations if variations is not None else titles.expand(title)
    seen: set[str] = set()
    out: list[str] = []
    for term in [title, *proposed]:
        cleaned = (term or "").strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _to_out(db: Session, target: SearchTarget, user: User) -> RoleOut:
    found = int(
        db.scalar(
            select(func.count())
            .select_from(JobListing)
            .where(JobListing.user_id == user.id, JobListing.matched_role == target.name)
        )
        or 0
    )
    terms = list(target.title_terms or [])
    return RoleOut(
        id=target.id,
        title=target.name,
        # The first term is the title itself; the rest are the variations.
        variations=terms[1:],
        location=target.location,
        remote=target.remote,
        salary_floor=target.salary_floor,
        schedule_minutes=target.schedule_minutes,
        last_run_at=target.last_run_at,
        listings_found=found,
    )


@router.get("/preview", response_model=RolePreview)
def preview_role(
    title: str = Query(min_length=1, max_length=200),
    user: User = Depends(get_current_user),
) -> RolePreview:
    """What would count as this role, without saving anything."""
    shape = titles.shape(title)
    proposed = titles.expand(title)
    return RolePreview(
        title=title.strip(),
        # The title itself leads the list everywhere else; here only the
        # alternatives are interesting.
        variations=[v for v in proposed if v.strip().lower() != title.strip().lower()],
        recognised=shape.recognised,
    )


@router.get("", response_model=list[RoleOut])
def list_roles(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[RoleOut]:
    targets = db.scalars(
        select(SearchTarget).where(SearchTarget.user_id == user.id).order_by(SearchTarget.id)
    ).all()
    return [_to_out(db, t, user) for t in targets]


@router.post("", response_model=RoleOut, status_code=201)
def create_role(
    payload: RoleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RoleOut:
    title = payload.title.strip()
    existing = db.scalar(
        select(SearchTarget).where(
            SearchTarget.user_id == user.id, func.lower(SearchTarget.name) == title.lower()
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have a role called “{title}”")
    target = SearchTarget(
        user_id=user.id,
        name=title,
        title_terms=_terms(title, payload.variations),
        location=payload.location,
        remote=payload.remote,
        salary_floor=payload.salary_floor,
        schedule_minutes=payload.schedule_minutes,
        notify_new=True,
        sources=[],  # every configured source
        exclusions=[],
    )
    db.add(target)
    db.flush()
    log.info("roles.created", user_id=user.id, role=title, terms=len(target.title_terms))
    return _to_out(db, target, user)


@router.put("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    payload: RoleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoleOut:
    target = db.get(SearchTarget, role_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    title = payload.title.strip()
    # Editing the variations must not silently re-propose them: when the client
    # sends a list, that list is the answer, empty included.
    target.name = title
    target.title_terms = _terms(title, payload.variations)
    target.location = payload.location
    target.remote = payload.remote
    target.salary_floor = payload.salary_floor
    target.schedule_minutes = payload.schedule_minutes
    return _to_out(db, target, user)


@router.delete("/{role_id}", response_model=OkResponse)
def delete_role(
    role_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    target = db.get(SearchTarget, role_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    # Listings already found are kept: they are jobs the user may still want,
    # and matched_role stays as the record of why they arrived.
    db.delete(target)
    return OkResponse()
