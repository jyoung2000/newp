from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SearchTarget, SourceState, User
from app.schemas.auth import OkResponse
from app.services.search_service import get_run, start_search_thread
from app.sources import NotImplementedSource, get_sources
from app.sources.base import SearchQuery

router = APIRouter()


class SearchRequest(BaseModel):
    terms: list[str] = Field(min_length=1)
    location: str | None = None
    remote: bool | None = None
    salary_floor: int | None = Field(default=None, ge=0)
    education_level: str | None = None
    posted_within_days: int | None = Field(default=None, ge=1, le=365)
    sources: list[str] = Field(default_factory=list)  # empty = all usable
    save_as: str | None = None  # also save as a search target


class SearchStarted(BaseModel):
    run_id: str


class SearchRunStatus(BaseModel):
    run_id: str
    status: str
    total_sources: int
    completed_sources: int
    found: int
    new: int
    per_source: dict[str, dict[str, Any]]
    error: str | None = None


@router.post("/run", response_model=SearchStarted)
def run_search(
    payload: SearchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SearchStarted:
    query = SearchQuery(
        terms=[t.strip() for t in payload.terms if t.strip()],
        location=payload.location,
        remote=payload.remote,
        salary_floor=payload.salary_floor,
        education_level=payload.education_level,
        posted_within_days=payload.posted_within_days,
    )
    if not query.terms:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one term required")
    if payload.save_as:
        db.add(
            SearchTarget(
                user_id=user.id,
                name=payload.save_as,
                title_terms=query.terms,
                location=payload.location,
                remote=payload.remote,
                salary_floor=payload.salary_floor,
                education_level=payload.education_level,
                posted_within_days=payload.posted_within_days,
                sources=payload.sources,
            )
        )
        db.commit()
    run_id = start_search_thread(user.id, query, payload.sources)
    return SearchStarted(run_id=run_id)


@router.get("/runs/{run_id}", response_model=SearchRunStatus)
def run_status(run_id: str, user: User = Depends(get_current_user)) -> SearchRunStatus:
    run = get_run(run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return SearchRunStatus(
        run_id=run.id,
        status=run.status,
        total_sources=run.total_sources,
        completed_sources=run.completed_sources,
        found=run.found,
        new=run.new,
        per_source=run.per_source,
        error=run.error,
    )


class SourceInfo(BaseModel):
    name: str
    label: str
    permission_basis: str
    requires_key: bool
    configured: bool
    forbidden: bool
    status: str  # ok / blocked / disabled / forbidden / unknown
    detail: str | None = None
    blocked_until: dt.datetime | None = None


@router.get("/sources", response_model=list[SourceInfo])
def list_sources(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SourceInfo]:
    states = {
        s.source: s
        for s in db.scalars(select(SourceState).where(SourceState.user_id == user.id))
    }
    infos = []
    for source in get_sources():
        forbidden = isinstance(source, NotImplementedSource)
        state = states.get(source.name)
        if forbidden:
            status_str = "forbidden"
        elif not source.is_configured():
            status_str = "disabled"
        elif state is not None:
            status_str = state.status
        else:
            status_str = "ok"
        infos.append(
            SourceInfo(
                name=source.name,
                label=source.label,
                permission_basis=source.permission_basis,
                requires_key=source.requires_key,
                configured=source.is_configured(),
                forbidden=forbidden,
                status=status_str,
                detail=state.detail if state else None,
                blocked_until=state.blocked_until if state else None,
            )
        )
    return infos


# --- Saved search targets ---------------------------------------------------


class SearchTargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title_terms: list[str] = Field(min_length=1)
    location: str | None = None
    remote: bool | None = None
    salary_floor: int | None = None
    education_level: str | None = None
    posted_within_days: int | None = None
    exclusions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    schedule_minutes: int | None = Field(default=None, ge=30)
    notify_new: bool = True


class SearchTargetOut(SearchTargetIn):
    id: int
    last_run_at: dt.datetime | None

    model_config = {"from_attributes": True}


@router.get("/targets", response_model=list[SearchTargetOut])
def list_targets(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SearchTarget]:
    return list(
        db.scalars(
            select(SearchTarget).where(SearchTarget.user_id == user.id).order_by(SearchTarget.id)
        )
    )


@router.post("/targets", response_model=SearchTargetOut, status_code=201)
def create_target(
    payload: SearchTargetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SearchTarget:
    row = SearchTarget(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


@router.put("/targets/{target_id}", response_model=SearchTargetOut)
def update_target(
    target_id: int,
    payload: SearchTargetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchTarget:
    row = db.get(SearchTarget, target_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    return row


@router.delete("/targets/{target_id}", response_model=OkResponse)
def delete_target(
    target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(SearchTarget, target_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()


@router.post("/targets/{target_id}/run", response_model=SearchStarted)
def run_target(
    target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SearchStarted:
    row = db.get(SearchTarget, target_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.last_run_at = dt.datetime.now(dt.UTC)
    db.commit()
    query = SearchQuery(
        terms=row.title_terms,
        location=row.location,
        remote=row.remote,
        salary_floor=row.salary_floor,
        education_level=row.education_level,
        posted_within_days=row.posted_within_days,
    )
    return SearchStarted(run_id=start_search_thread(user.id, query, row.sources))
