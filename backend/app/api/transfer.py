from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.logging_conf import get_logger
from app.models import Application, JobListing, User, utcnow
from app.services import transfer
from app.services.storage import resolve_user_path

log = get_logger(__name__)
router = APIRouter()

LISTING_FIELDS = [
    "id", "source", "title", "company", "location", "remote", "salary_min",
    "salary_max", "salary_currency", "salary_period", "education_level",
    "match_score", "posted_at", "url", "apply_url", "summary",
]
APPLICATION_FIELDS = [
    "id", "title", "company", "source", "status", "mode", "executor",
    "submitted_at", "outcome", "url", "created_at",
]


@router.get("/profile.json")
def export_profile_json(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = transfer.export_profile(db, user)
    data["exported_at"] = utcnow().isoformat()
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=jobpilot-profile.json"},
    )


@router.get("/listings.csv")
def export_listings_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listings = list(db.scalars(select(JobListing).where(JobListing.user_id == user.id)))
    rows = transfer.listings_to_rows(listings)
    csv_text = transfer.rows_to_csv(rows, LISTING_FIELDS)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobpilot-listings.csv"},
    )


@router.get("/listings.json")
def export_listings_json(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listings = list(db.scalars(select(JobListing).where(JobListing.user_id == user.id)))
    return Response(
        content=json.dumps(transfer.listings_to_rows(listings), indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=jobpilot-listings.json"},
    )


@router.get("/applications.csv")
def export_applications_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = list(db.scalars(select(Application).where(Application.user_id == user.id)))
    listings = {
        li.id: li
        for li in db.scalars(
            select(JobListing).where(JobListing.id.in_({a.listing_id for a in apps}))
        )
    }
    rows = transfer.applications_to_rows(db, apps, listings)
    return Response(
        content=transfer.rows_to_csv(rows, APPLICATION_FIELDS),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobpilot-applications.csv"},
    )


@router.get("/everything.zip")
def export_everything(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A complete zip: profile JSON, job lists (CSV+JSON), application
    history CSV, and every uploaded file."""
    from app.models import StoredFile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = transfer.export_profile(db, user)
        profile["exported_at"] = utcnow().isoformat()
        zf.writestr("profile.json", json.dumps(profile, indent=2))

        listings = list(db.scalars(select(JobListing).where(JobListing.user_id == user.id)))
        listing_rows = transfer.listings_to_rows(listings)
        zf.writestr("listings.csv", transfer.rows_to_csv(listing_rows, LISTING_FIELDS))
        zf.writestr("listings.json", json.dumps(listing_rows, indent=2))

        apps = list(db.scalars(select(Application).where(Application.user_id == user.id)))
        listing_map = {li.id: li for li in listings}
        app_rows = transfer.applications_to_rows(db, apps, listing_map)
        zf.writestr("applications.csv", transfer.rows_to_csv(app_rows, APPLICATION_FIELDS))

        for file_row in db.scalars(
            select(StoredFile).where(
                StoredFile.user_id == user.id, StoredFile.kind != "screenshot"
            )
        ):
            try:
                path = resolve_user_path(user.id, file_row.path)
                if path.is_file():
                    zf.write(path, f"files/{file_row.kind}/{file_row.id}_{file_row.filename}")
            except (PermissionError, OSError):
                continue
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=jobpilot-export.zip"},
    )


# --- Import -----------------------------------------------------------------


class ImportPreview(BaseModel):
    profile_fields: dict[str, Any]
    work_experiences: int
    educations: int
    recommendations: int
    custom_fields: int
    saved_answers: int
    search_targets: int
    conflicts: dict[str, list[str]]


@router.post("/profile/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportPreview:
    """Merge preview diff: what would change, and where the import conflicts
    with values already set (so the user can decide before applying)."""
    from app.models import CustomField, Profile, SavedAnswer

    data = json.loads((await file.read()).decode())
    incoming = data.get("profile", {})
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None

    profile_diff: dict[str, Any] = {}
    conflicts: dict[str, list[str]] = {"profile": [], "custom_fields": [], "saved_answers": []}
    for field, value in incoming.items():
        if not hasattr(profile, field):
            continue
        current = getattr(profile, field)
        if current != value:
            profile_diff[field] = {"current": transfer._iso(current), "incoming": value}
            if current not in (None, "", [], {}):
                conflicts["profile"].append(field)

    existing_cf = {c.key for c in db.scalars(select(CustomField).where(CustomField.user_id == user.id))}
    for row in data.get("custom_fields", []):
        if row.get("key") in existing_cf:
            conflicts["custom_fields"].append(row["key"])
    existing_sa = {
        s.question_key for s in db.scalars(select(SavedAnswer).where(SavedAnswer.user_id == user.id))
    }
    for row in data.get("saved_answers", []):
        if row.get("question_key") in existing_sa:
            conflicts["saved_answers"].append(row["question_key"])

    return ImportPreview(
        profile_fields=profile_diff,
        work_experiences=len(data.get("work_experiences", [])),
        educations=len(data.get("educations", [])),
        recommendations=len(data.get("recommendations", [])),
        custom_fields=len(data.get("custom_fields", [])),
        saved_answers=len(data.get("saved_answers", [])),
        search_targets=len(data.get("search_targets", [])),
        conflicts=conflicts,
    )


class ImportResult(BaseModel):
    applied: dict[str, int]


@router.post("/profile/apply", response_model=ImportResult)
async def apply_import(
    file: UploadFile = File(...),
    merge: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    data = json.loads((await file.read()).decode())
    counts = transfer.import_profile(db, user, data, merge=merge)
    log.info("transfer.imported", user_id=user.id, counts=counts, merge=merge)
    return ImportResult(applied=counts)


class ImportListingsResult(BaseModel):
    imported: int
    skipped: int


@router.post("/listings/import", response_model=ImportListingsResult)
async def import_listings(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportListingsResult:
    """Import job lists (CSV or JSON). Column mapping is by header name; a
    'url' + 'title' + 'company' are the minimum."""
    from app.services.ingest import upsert_listings
    from app.sources.base import RawListing

    raw_bytes = await file.read()
    text = raw_bytes.decode()
    if file.filename and file.filename.endswith(".json"):
        records = json.loads(text)
    else:
        records = transfer.parse_listings_csv(text)

    listings = []
    skipped = 0
    for record in records:
        url = record.get("url") or record.get("canonical_url") or record.get("apply_url")
        title = record.get("title")
        company = record.get("company")
        if not (title and company):
            skipped += 1
            continue
        listings.append(
            RawListing(
                source=record.get("source", "import"),
                url=url or f"import://{title}-{company}",
                apply_url=record.get("apply_url") or url,
                title=title,
                company=company,
                location=record.get("location"),
                salary_raw=record.get("salary_raw"),
                salary_min=_int(record.get("salary_min")),
                salary_max=_int(record.get("salary_max")),
                salary_currency=record.get("salary_currency") or None,
                education_level=record.get("education_level") or None,
                description=record.get("summary") or record.get("description"),
            )
        )
    new_rows, dupes = upsert_listings(db, user, listings)
    return ImportListingsResult(imported=len(new_rows), skipped=skipped + dupes)


def _int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None
