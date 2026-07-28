from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.llm import tasks as llm_tasks
from app.llm.schemas import ParsedResume
from app.logging_conf import get_logger
from app.models import (
    FILE_KINDS,
    Education,
    Profile,
    StoredFile,
    User,
    WorkExperience,
)
from app.schemas.auth import OkResponse
from app.services.extract import extract_text
from app.services.storage import delete_file, resolve_user_path, store_bytes

log = get_logger(__name__)
router = APIRouter()

STATIC_EXT_DIR = Path(__file__).resolve().parents[1] / "static" / "extension"


class FileOut(BaseModel):
    id: int
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    is_default_resume: bool
    parse_confirmed: bool
    has_parse: bool = False
    has_text: bool = False
    created_at: dt.datetime

    model_config = {"from_attributes": True}


def _to_out(row: StoredFile) -> FileOut:
    out = FileOut.model_validate(row)
    out.has_parse = row.parsed_json is not None
    out.has_text = bool(row.extracted_text)
    return out


@router.get("", response_model=list[FileOut])
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[FileOut]:
    rows = db.scalars(
        select(StoredFile)
        .where(StoredFile.user_id == user.id, StoredFile.kind != "screenshot")
        .order_by(StoredFile.created_at.desc())
    ).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=FileOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    kind: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileOut:
    if kind not in FILE_KINDS or kind == "screenshot":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"kind must be one of {FILE_KINDS[:-1]}")
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {get_settings().max_upload_mb} MB",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    rel_path = store_bytes(user.id, kind, file.filename or "upload", data)
    row = StoredFile(
        user_id=user.id,
        kind=kind,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        path=rel_path,
        extracted_text=extract_text(data, file.content_type or "", file.filename or ""),
    )
    # First resume automatically becomes the default.
    if kind == "resume":
        existing_default = db.scalar(
            select(StoredFile).where(
                StoredFile.user_id == user.id,
                StoredFile.kind == "resume",
                StoredFile.is_default_resume.is_(True),
            )
        )
        row.is_default_resume = existing_default is None
    db.add(row)
    db.flush()
    log.info("files.uploaded", user_id=user.id, file_id=row.id, kind=kind, size=len(data))
    return _to_out(row)


def _owned_file(db: Session, user: User, file_id: int) -> StoredFile:
    row = db.get(StoredFile, file_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return row


@router.get("/{file_id}/download")
def download_file(
    file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> FileResponse:
    row = _owned_file(db, user, file_id)
    try:
        path = resolve_user_path(user.id, row.path)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Path scoping violation") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File data missing")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)


@router.delete("/{file_id}", response_model=OkResponse)
def remove_file(
    file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = _owned_file(db, user, file_id)
    delete_file(user.id, row.path)
    db.delete(row)
    return OkResponse()


@router.post("/{file_id}/default-resume", response_model=OkResponse)
def set_default_resume(
    file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = _owned_file(db, user, file_id)
    if row.kind != "resume":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only resumes can be the default resume")
    for other in db.scalars(
        select(StoredFile).where(StoredFile.user_id == user.id, StoredFile.kind == "resume")
    ):
        other.is_default_resume = other.id == row.id
    return OkResponse()


# --- Resume parsing (review-the-parse flow) ---------------------------------


@router.post("/{file_id}/parse", response_model=ParsedResume)
def parse_resume(
    file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ParsedResume:
    """Run the LLM parse and store it UNCONFIRMED. The user reviews and
    corrects the result before anything uses it — never silently trusted."""
    row = _owned_file(db, user, file_id)
    if row.kind != "resume":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only resumes can be parsed")
    if not row.extracted_text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No text could be extracted from this file; upload a PDF, DOCX, TXT or MD resume",
        )
    parsed = llm_tasks.parse_resume(row.extracted_text)
    row.parsed_json = parsed.model_dump()
    row.parse_confirmed = False
    return parsed


class ConfirmParseRequest(BaseModel):
    parsed: ParsedResume
    # Merge behavior: fill blanks in the profile, and only replace work
    # history / education when the user opts in.
    replace_work_history: bool = False
    replace_education: bool = False


@router.post("/{file_id}/confirm-parse", response_model=OkResponse)
def confirm_parse(
    file_id: int,
    payload: ConfirmParseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Apply the user-reviewed (and possibly corrected) parse."""
    row = _owned_file(db, user, file_id)
    parsed = payload.parsed
    row.parsed_json = parsed.model_dump()
    row.parse_confirmed = True

    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None

    def fill_blank(attr: str, value: Any) -> None:
        if value and not getattr(profile, attr):
            setattr(profile, attr, value)

    c = parsed.contact
    fill_blank("first_name", c.first_name)
    fill_blank("last_name", c.last_name)
    fill_blank("email", c.email)
    fill_blank("phone", c.phone)
    fill_blank("city", c.city)
    fill_blank("state", c.state)
    fill_blank("country", c.country)
    fill_blank("linkedin_url", c.linkedin_url)
    fill_blank("github_url", c.github_url)
    fill_blank("website_url", c.website_url)
    if parsed.total_years_experience and profile.total_years_experience is None:
        profile.total_years_experience = parsed.total_years_experience

    # Skills confirmed by the user through this review become usable answers.
    skills = dict(profile.skills_years or {})
    for skill in parsed.skills:
        if skill.years is not None:
            skills[skill.name] = {"years": skill.years, "confirmed": True}
    profile.skills_years = skills

    existing_work = list(
        db.scalars(select(WorkExperience).where(WorkExperience.user_id == user.id))
    )
    if payload.replace_work_history:
        for old in existing_work:
            db.delete(old)
        existing_work = []
    if not existing_work:
        for index, exp in enumerate(parsed.work_experiences):
            db.add(
                WorkExperience(
                    user_id=user.id,
                    title=exp.title,
                    company=exp.company,
                    location=exp.location,
                    start_date=_parse_date(exp.start_date),
                    end_date=_parse_date(exp.end_date),
                    is_current=exp.is_current,
                    bullets=exp.bullets,
                    order_index=index,
                )
            )

    existing_edu = list(db.scalars(select(Education).where(Education.user_id == user.id)))
    if payload.replace_education:
        for old_edu in existing_edu:
            db.delete(old_edu)
        existing_edu = []
    if not existing_edu:
        for index, edu in enumerate(parsed.educations):
            db.add(
                Education(
                    user_id=user.id,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    school=edu.school,
                    start_date=_parse_date(edu.start_date),
                    end_date=_parse_date(edu.end_date),
                    gpa=edu.gpa,
                    order_index=index,
                )
            )
    log.info("files.parse_confirmed", user_id=user.id, file_id=row.id)
    return OkResponse()


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# --- Extension bundle downloads (see Settings → Extension) ------------------


def extension_bundle_version() -> str | None:
    version_file = STATIC_EXT_DIR / "VERSION"
    if version_file.is_file():
        return version_file.read_text().strip()
    return None


class ExtensionInfo(BaseModel):
    available: bool
    version: str | None = None
    chrome_url: str | None = None
    firefox_url: str | None = None


@router.get("/extension/info", response_model=ExtensionInfo)
def extension_info(user: User = Depends(get_current_user)) -> ExtensionInfo:
    chrome = STATIC_EXT_DIR / "jobpilot-chrome.zip"
    firefox = STATIC_EXT_DIR / "jobpilot-firefox.zip"
    version = extension_bundle_version()
    return ExtensionInfo(
        available=chrome.is_file() or firefox.is_file(),
        version=version,
        chrome_url="/api/files/extension/chrome" if chrome.is_file() else None,
        firefox_url="/api/files/extension/firefox" if firefox.is_file() else None,
    )


@router.get("/extension/{browser}")
def download_extension(browser: str, user: User = Depends(get_current_user)) -> FileResponse:
    if browser not in ("chrome", "firefox"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown browser")
    path = STATIC_EXT_DIR / f"jobpilot-{browser}.zip"
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Extension bundle not built. Run `make ext-zip` or use the Docker image.",
        )
    return FileResponse(path, media_type="application/zip", filename=f"jobpilot-{browser}.zip")
