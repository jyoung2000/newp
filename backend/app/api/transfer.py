from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db
from app.deps import get_current_user
from app.logging_conf import get_logger
from app.models import Application, JobListing, StoredFile, User, utcnow
from app.services import transfer
from app.services.extract import extract_text
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
        # The CSV is the one a human opens in a spreadsheet, and it is lossy.
        # This is the one a restore reads: whole records, with a listing key so
        # each application can be re-attached after import.
        app_records = transfer.applications_to_records(apps, listing_map)
        zf.writestr("applications.json", json.dumps(app_records, indent=2))

        file_rows = list(
            db.scalars(
                select(StoredFile).where(
                    StoredFile.user_id == user.id, StoredFile.kind != "screenshot"
                )
            )
        )
        # Names inside files/ are ids-and-filenames, which say nothing about
        # which is the default résumé or what a parse confirmed. Restoring needs
        # that, so it travels separately and points at the archive entry.
        zf.writestr(
            "files.json",
            json.dumps(
                [
                    {
                        "entry": f"files/{f.kind}/{f.id}_{f.filename}",
                        "kind": f.kind,
                        "filename": f.filename,
                        "content_type": f.content_type,
                        "is_default_resume": f.is_default_resume,
                        "parse_confirmed": f.parse_confirmed,
                        "parsed_json": f.parsed_json,
                    }
                    for f in file_rows
                ],
                indent=2,
            ),
        )

        # Last, so it can count what actually went in. A restore reads this
        # first to decide whether the zip is a JobPilot backup at all.
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "jobpilot_backup_version": 1,
                    "app_version": __version__,
                    "exported_at": utcnow().isoformat(),
                    "account_email": user.email,
                    "counts": {
                        "listings": len(listings),
                        "applications": len(apps),
                        "files": len(file_rows),
                        "work_experiences": len(profile.get("work_experiences", [])),
                        "educations": len(profile.get("educations", [])),
                        "custom_fields": len(profile.get("custom_fields", [])),
                        "saved_answers": len(profile.get("saved_answers", [])),
                    },
                },
                indent=2,
            ),
        )

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


# --- Restore a full backup --------------------------------------------------
# The pieces above import one thing each. This restores the whole zip that
# everything.zip produced — profile, job list, application history and uploaded
# files — so a backup is something you can actually put back, on this install
# or a different one. Preview first: it says what is in the archive and what
# already exists, and changes nothing.

MAX_BACKUP_BYTES = 200 * 1024 * 1024


class BackupContents(BaseModel):
    valid: bool = True
    problem: str = ""
    app_version: str = ""
    exported_at: str = ""
    account_email: str = ""
    listings: int = 0
    applications: int = 0
    files: int = 0
    work_experiences: int = 0
    educations: int = 0
    custom_fields: int = 0
    saved_answers: int = 0
    # What restoring into this account would land on top of.
    existing_listings: int = 0
    existing_applications: int = 0
    existing_files: int = 0


class RestoreResult(BaseModel):
    profile_updated: bool = False
    listings_imported: int = 0
    listings_skipped: int = 0
    applications_imported: int = 0
    applications_skipped: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    notes: list[str] = []


def _open_backup(raw: bytes) -> tuple[zipfile.ZipFile | None, str]:
    if len(raw) > MAX_BACKUP_BYTES:
        return None, "That file is larger than the 200 MB restore limit."
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None, "That isn't a zip file. Upload the jobpilot-export.zip you downloaded."
    names = set(zf.namelist())
    if "manifest.json" not in names and "profile.json" not in names:
        return None, (
            "That zip doesn't look like a JobPilot backup — no manifest.json or "
            "profile.json inside."
        )
    return zf, ""


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(zf.read(name))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


@router.post("/backup/preview", response_model=BackupContents)
async def preview_backup(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BackupContents:
    zf, problem = _open_backup(await file.read())
    if zf is None:
        return BackupContents(valid=False, problem=problem)

    manifest = _read_json(zf, "manifest.json") or {}
    profile = _read_json(zf, "profile.json") or {}
    listings = _read_json(zf, "listings.json") or []
    apps = _read_json(zf, "applications.json") or []
    files = _read_json(zf, "files.json") or []
    counts = manifest.get("counts") or {}

    def existing(model: Any) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id)) or 0)

    return BackupContents(
        app_version=str(manifest.get("app_version", "")),
        exported_at=str(manifest.get("exported_at", profile.get("exported_at") or "")),
        account_email=str(manifest.get("account_email", "")),
        # Prefer the payloads themselves over the manifest's counts: an older
        # backup has no manifest, and a hand-edited one may disagree with it.
        listings=len(listings) if listings else int(counts.get("listings", 0)),
        applications=len(apps) if apps else int(counts.get("applications", 0)),
        files=len(files) if files else int(counts.get("files", 0)),
        work_experiences=len(profile.get("work_experiences") or []),
        educations=len(profile.get("educations") or []),
        custom_fields=len(profile.get("custom_fields") or []),
        saved_answers=len(profile.get("saved_answers") or []),
        existing_listings=existing(JobListing),
        existing_applications=existing(Application),
        existing_files=existing(StoredFile),
    )


@router.post("/backup/restore", response_model=RestoreResult)
async def restore_backup(
    file: UploadFile = File(...),
    merge: str = Query("keep", pattern="^(keep|overwrite)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestoreResult:
    """Put a backup back. Additive by design: nothing already in the account is
    deleted. `merge=overwrite` lets profile values from the backup win where
    they collide; `keep` (the default) preserves what is already here.

    Listings de-duplicate through the same upsert the importer uses, and an
    application is skipped when one already exists for the same listing — so
    running a restore twice does not double the history."""
    from app.services.ingest import upsert_listings
    from app.services.storage import store_bytes
    from app.sources.base import RawListing

    zf, problem = _open_backup(await file.read())
    if zf is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    result = RestoreResult(notes=[])

    # 1. Profile, custom fields, saved answers, search targets.
    profile_payload = _read_json(zf, "profile.json")
    if profile_payload:
        # import_profile's bool: True fills blanks and adds (keep what is
        # here), False replaces wholesale (let the backup win).
        transfer.import_profile(db, user, profile_payload, merge=(merge == "keep"))
        result.profile_updated = True
    else:
        result.notes.append("No profile.json in the archive; profile left alone.")

    # 2. Job list. Reuse the upsert so duplicates collapse the same way an
    #    ordinary import's would.
    listing_records = _read_json(zf, "listings.json") or []
    raw_listings = []
    for record in listing_records:
        title, company = record.get("title"), record.get("company")
        if not (title and company):
            result.listings_skipped += 1
            continue
        url = record.get("url") or record.get("canonical_url") or record.get("apply_url")
        raw_listings.append(
            RawListing(
                source=record.get("source") or "import",
                url=url or f"import://{title}-{company}",
                apply_url=record.get("apply_url") or url,
                title=title,
                company=company,
                location=record.get("location"),
                salary_min=_int(record.get("salary_min")),
                salary_max=_int(record.get("salary_max")),
                salary_currency=record.get("salary_currency") or None,
                education_level=record.get("education_level") or None,
                description=record.get("summary") or record.get("description"),
            )
        )
    if raw_listings:
        new_rows, dupes = upsert_listings(db, user, raw_listings)
        result.listings_imported = len(new_rows)
        result.listings_skipped += dupes
        db.flush()

    # 3. Application history, re-attached to listings by key rather than by id.
    app_records = _read_json(zf, "applications.json") or []
    if app_records:
        by_key = {
            transfer.listing_key(li): li
            for li in db.scalars(select(JobListing).where(JobListing.user_id == user.id))
        }
        existing_pairs = {
            (a.listing_id, a.status, a.outcome)
            for a in db.scalars(select(Application).where(Application.user_id == user.id))
        }
        for record in app_records:
            listing = by_key.get(record.get("listing_key") or "")
            if listing is None:
                # The backup's listings didn't cover it (or came from an older
                # export). Recreate a minimal listing so the history survives
                # rather than being dropped on the floor.
                stub = record.get("listing") or {}
                if not (stub.get("title") and stub.get("company")):
                    result.applications_skipped += 1
                    continue
                created, _ = upsert_listings(
                    db,
                    user,
                    [
                        RawListing(
                            source=stub.get("source") or "import",
                            url=stub.get("canonical_url")
                            or f"import://{stub['title']}-{stub['company']}",
                            apply_url=stub.get("canonical_url"),
                            title=stub["title"],
                            company=stub["company"],
                            location=stub.get("location"),
                        )
                    ],
                )
                db.flush()
                if not created:
                    result.applications_skipped += 1
                    continue
                listing = created[0]
                by_key[transfer.listing_key(listing)] = listing

            key = (listing.id, record.get("status") or "draft", record.get("outcome") or "none")
            if key in existing_pairs:
                result.applications_skipped += 1
                continue
            db.add(
                Application(
                    user_id=user.id,
                    listing_id=listing.id,
                    status=record.get("status") or "draft",
                    mode=record.get("mode") or "review",
                    executor=record.get("executor"),
                    humanize=record.get("humanize"),
                    needs_human_reason=record.get("needs_human_reason"),
                    parked_at=transfer.parse_dt(record.get("parked_at")),
                    submitted_at=transfer.parse_dt(record.get("submitted_at")),
                    outcome=record.get("outcome") or "none",
                    outcome_updated_at=transfer.parse_dt(record.get("outcome_updated_at")),
                    error=record.get("error"),
                    field_snapshot=record.get("field_snapshot"),
                )
            )
            existing_pairs.add(key)
            result.applications_imported += 1

    # 4. Uploaded files — résumés and cover letters, with their bytes.
    file_records = _read_json(zf, "files.json") or []
    names = set(zf.namelist())
    have_default_resume = db.scalar(
        select(StoredFile.id).where(
            StoredFile.user_id == user.id,
            StoredFile.kind == "resume",
            StoredFile.is_default_resume.is_(True),
        )
    )
    existing_names = {
        (f.kind, f.filename)
        for f in db.scalars(select(StoredFile).where(StoredFile.user_id == user.id))
    }
    for record in file_records:
        entry = record.get("entry")
        if not entry or entry not in names:
            result.files_skipped += 1
            continue
        kind = record.get("kind") or "other"
        filename = record.get("filename") or "restored"
        if (kind, filename) in existing_names:
            result.files_skipped += 1
            continue
        try:
            data = zf.read(entry)
        except KeyError:
            result.files_skipped += 1
            continue
        rel_path = store_bytes(user.id, kind, filename, data)
        row = StoredFile(
            user_id=user.id,
            kind=kind,
            filename=filename,
            content_type=record.get("content_type") or "application/octet-stream",
            size_bytes=len(data),
            path=rel_path,
            parsed_json=record.get("parsed_json"),
            parse_confirmed=bool(record.get("parse_confirmed")),
            extracted_text=extract_text(data, record.get("content_type") or "", filename),
            # Only one résumé can be the default, and an account that already
            # has one keeps it.
            is_default_resume=bool(record.get("is_default_resume")) and not have_default_resume,
        )
        if row.is_default_resume:
            have_default_resume = -1  # claimed by this restore
        db.add(row)
        existing_names.add((kind, filename))
        result.files_imported += 1

    log.info(
        "transfer.restored",
        user_id=user.id,
        listings=result.listings_imported,
        applications=result.applications_imported,
        files=result.files_imported,
    )
    return result


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
