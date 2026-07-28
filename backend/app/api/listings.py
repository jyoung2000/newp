from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Application, DiscoveredOrg, JobListing, User, utcnow
from app.schemas.auth import OkResponse
from app.services.ingest import canonicalize_url, enrich_listings, upsert_listings
from app.sources.base import RawListing
from app.sources.http import RobotsDisallowedError, SourceBlockedError, get_http
from app.sources.jsonld import fetch_jobpostings
from app.sources.websearch import harvest_org_refs

router = APIRouter()


class ListingOut(BaseModel):
    id: int
    source: str
    canonical_url: str
    apply_url: str | None
    title: str
    company: str
    location: str | None
    remote: bool | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    salary_raw: str | None
    education_level: str | None
    posted_at: dt.datetime | None
    summary: str | None
    requirements: list[str]
    match_score: int | None
    match_rationale: str | None
    fetched_at: dt.datetime | None
    applied: bool = False
    application_id: int | None = None

    model_config = {"from_attributes": True}


class ListingDetail(ListingOut):
    description: str | None
    extra: dict[str, Any]


def _with_application_flags(
    db: Session, user: User, rows: list[JobListing]
) -> list[ListingOut]:
    apps = {
        a.listing_id: a
        for a in db.scalars(select(Application).where(Application.user_id == user.id))
    }
    out = []
    for row in rows:
        item = ListingOut.model_validate(row)
        app = apps.get(row.id)
        if app is not None:
            item.applied = True
            item.application_id = app.id
        out.append(item)
    return out


@router.get("", response_model=list[ListingOut])
def list_listings(
    q: str | None = None,
    source: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    remote: bool | None = None,
    sort: str = Query(default="score", pattern="^(score|posted|salary|company|fetched)$"),
    limit: int = Query(default=200, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ListingOut]:
    stmt = select(JobListing).where(JobListing.user_id == user.id)
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                JobListing.title.ilike(needle),
                JobListing.company.ilike(needle),
                JobListing.description.ilike(needle),
            )
        )
    if source:
        stmt = stmt.where(JobListing.source == source)
    if min_score is not None:
        stmt = stmt.where(JobListing.match_score >= min_score)
    if remote is not None:
        stmt = stmt.where(JobListing.remote.is_(remote))
    from sqlalchemy.sql.elements import ColumnElement

    orders: dict[str, ColumnElement] = {
        "score": JobListing.match_score.desc().nulls_last(),
        "posted": JobListing.posted_at.desc().nulls_last(),
        "salary": JobListing.salary_max.desc().nulls_last(),
        "company": JobListing.company.asc(),
        "fetched": JobListing.fetched_at.desc().nulls_last(),
    }
    order = orders[sort]
    rows = list(db.scalars(stmt.order_by(order, JobListing.id.desc()).limit(limit)))
    return _with_application_flags(db, user, rows)


@router.get("/{listing_id}", response_model=ListingDetail)
def get_listing(
    listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ListingDetail:
    row = db.get(JobListing, listing_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    detail = ListingDetail.model_validate(row)
    app = db.scalar(
        select(Application).where(
            Application.user_id == user.id, Application.listing_id == row.id
        )
    )
    if app is not None:
        detail.applied = True
        detail.application_id = app.id
    return detail


@router.delete("/{listing_id}", response_model=OkResponse)
def delete_listing(
    listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(JobListing, listing_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()


class ManualAddRequest(BaseModel):
    """Paste a URL (fetched robots-permitting, parsed for JSON-LD) and/or the
    listing's details directly — including listings from boards JobPilot
    won't fetch itself."""

    url: str | None = None
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = None
    description: str | None = None
    salary_raw: str | None = None
    apply_url: str | None = None


@router.post("/manual", response_model=ListingDetail, status_code=201)
def add_manual(
    payload: ManualAddRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ListingDetail:
    if not payload.url and not (payload.title and payload.company):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide a URL, or at least a title and company",
        )
    fetched: RawListing | None = None
    fetch_note: str | None = None
    if payload.url:
        try:
            postings = fetch_jobpostings(payload.url, get_http())
            fetched = postings[0] if postings else None
        except RobotsDisallowedError:
            fetch_note = "robots.txt disallows fetching this page; stored what you provided"
        except SourceBlockedError as exc:
            fetch_note = f"page not fetchable ({exc.reason}); stored what you provided"
        except Exception:
            fetch_note = "page fetch failed; stored what you provided"
        # Grow the org-slug table from manually pasted ATS URLs.
        for ref in harvest_org_refs([payload.url]):
            existing = db.scalar(
                select(DiscoveredOrg).where(
                    DiscoveredOrg.user_id == user.id,
                    DiscoveredOrg.ats == ref.ats,
                    DiscoveredOrg.slug == ref.slug,
                )
            )
            if existing is None:
                db.add(
                    DiscoveredOrg(
                        user_id=user.id, ats=ref.ats, slug=ref.slug, last_seen_at=utcnow()
                    )
                )

    title = payload.title or (fetched.title if fetched else None)
    company = payload.company or (fetched.company if fetched else None)
    if not title or not company:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Could not extract title/company from the URL"
            + (f" ({fetch_note})" if fetch_note else "")
            + "; please provide them",
        )
    from app.services.salary import parse_salary

    salary = parse_salary(payload.salary_raw or (fetched.salary_raw if fetched else None))
    raw = RawListing(
        source="manual",
        url=payload.url or f"manual://{utcnow().timestamp()}",
        apply_url=payload.apply_url or (fetched.apply_url if fetched else payload.url),
        title=title,
        company=company,
        location=payload.location or (fetched.location if fetched else None),
        remote=fetched.remote if fetched else None,
        description=payload.description or (fetched.description if fetched else None),
        salary_raw=payload.salary_raw or (fetched.salary_raw if fetched else None),
        salary_min=fetched.salary_min if fetched else salary.minimum,
        salary_max=fetched.salary_max if fetched else salary.maximum,
        salary_currency=fetched.salary_currency if fetched else salary.currency,
        salary_period=fetched.salary_period if fetched else salary.period,
        education_level=fetched.education_level if fetched else None,
        posted_at=fetched.posted_at if fetched else None,
    )
    existing_listing = db.scalar(
        select(JobListing).where(
            JobListing.user_id == user.id,
            JobListing.canonical_url == canonicalize_url(raw.url),
        )
    )
    if existing_listing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This listing is already saved")
    new_rows, _ = upsert_listings(db, user, [raw])
    enrich_listings(db, user, new_rows, limit=1)
    db.commit()
    return get_listing(new_rows[0].id, user, db)
