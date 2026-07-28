"""Endpoints the browser extension talks to.

Pairing is the only unauthenticated call (it consumes a one-time code); all
others require the device token issued at pairing (Authorization: Bearer).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db
from app.deps import get_device, get_device_user
from app.executor.states import InvalidTransitionError, record_event, transition
from app.logging_conf import get_logger
from app.models import (
    Application,
    Device,
    Intervention,
    JobListing,
    PairingCode,
    RunBatch,
    User,
    utcnow,
)
from app.schemas.auth import OkResponse, UserSettings
from app.security import hash_token, new_token
from app.services.intervention_service import create_intervention
from app.services.pacing import check_submission_allowance
from app.services.resolver import DetectedField as ResolverField
from app.services.resolver import mark_answer_used, resolve_field
from app.services.storage import store_bytes

log = get_logger(__name__)
router = APIRouter()


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    name: str = Field(min_length=1, max_length=200)
    browser: str | None = None
    extension_version: str | None = None


class PairResponse(BaseModel):
    token: str
    device_id: int
    user_email: str
    server_version: str


@router.post("/pair", response_model=PairResponse)
def pair(payload: PairRequest, db: Session = Depends(get_db)) -> PairResponse:
    row = db.scalar(
        select(PairingCode).where(
            PairingCode.code_hash == hash_token(payload.code), PairingCode.used.is_(False)
        )
    )
    now = utcnow()
    if row is not None:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.UTC)
        if expires < now:
            row = None
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired pairing code")
    row.used = True
    token = new_token()
    device = Device(
        user_id=row.user_id,
        name=payload.name,
        browser=payload.browser,
        token_hash=hash_token(token),
        last_seen_at=now,
        extension_version=payload.extension_version,
    )
    db.add(device)
    db.flush()
    user = db.get(User, row.user_id)
    assert user is not None
    log.info("ext.paired", user_id=user.id, device_id=device.id, browser=payload.browser)
    return PairResponse(
        token=token, device_id=device.id, user_email=user.email, server_version=__version__
    )


class PingResponse(BaseModel):
    ok: bool = True
    user_email: str
    device_id: int
    device_name: str
    server_version: str
    latest_extension_version: str | None = None


@router.get("/ping", response_model=PingResponse)
def ping(
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
) -> PingResponse:
    from app.api.files import extension_bundle_version

    return PingResponse(
        user_email=user.email,
        device_id=device.id,
        device_name=device.name,
        server_version=__version__,
        latest_extension_version=extension_bundle_version(),
    )


# ---------------------------------------------------------------------------
# Job driving: the extension claims queued applications, resolves fields
# through the server-side resolver, raises interventions, and reports
# results. All state changes go through the server's state machine, and the
# throughput ceilings are enforced here — the client cannot bypass them.
# ---------------------------------------------------------------------------

class JobListingPayload(BaseModel):
    id: int
    title: str
    company: str
    apply_url: str | None
    canonical_url: str
    location: str | None


class NextJob(BaseModel):
    application_id: int
    mode: str
    humanize: bool
    resume: bool = False  # True when resuming a needs_human application
    listing: JobListingPayload
    intervention_wait_minutes: int


class NextJobResponse(BaseModel):
    job: NextJob | None = None
    waiting_reason: str | None = None
    retry_in_seconds: int = 30


@router.post("/next-job", response_model=NextJobResponse)
def next_job(
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> NextJobResponse:
    from app.config import get_settings

    pacing = check_submission_allowance(db, user.id)
    if not pacing.allowed:
        return NextJobResponse(waiting_reason=pacing.reason, retry_in_seconds=300)

    running_batches = select(RunBatch.id).where(
        RunBatch.user_id == user.id, RunBatch.status == "running"
    )
    # 1) Resume: needs_human apps whose interventions are all answered.
    resumable = db.scalar(
        select(Application)
        .where(
            Application.user_id == user.id,
            Application.status == "needs_human",
            Application.executor == "extension",
            Application.run_batch_id.in_(running_batches),
            ~Application.id.in_(
                select(Intervention.application_id).where(Intervention.status == "open")
            ),
        )
        .order_by(Application.updated_at)
    )
    app = resumable
    resume = app is not None
    if app is None:
        # 2) Fresh queued work assigned to the extension (or unassigned).
        from sqlalchemy import or_

        app = db.scalar(
            select(Application)
            .where(
                Application.user_id == user.id,
                Application.status == "queued",
                Application.run_batch_id.in_(running_batches),
                or_(Application.executor == "extension", Application.executor.is_(None)),
            )
            .order_by(Application.id)
        )
    if app is None:
        return NextJobResponse(waiting_reason="No queued applications", retry_in_seconds=60)

    listing = db.get(JobListing, app.listing_id)
    assert listing is not None
    if not resume:
        app.executor = "extension"
        try:
            transition(
                db, app, "filling", reason="claimed by extension",
                payload={"device_id": device.id}, actor="extension",
            )
        except InvalidTransitionError:  # pragma: no cover - claim race
            return NextJobResponse(waiting_reason="Claim race, retry", retry_in_seconds=5)
    settings_obj = UserSettings.model_validate(
        {**UserSettings().model_dump(), **(user.settings or {})}
    )
    humanize = app.humanize if app.humanize is not None else settings_obj.humanize_default
    return NextJobResponse(
        job=NextJob(
            application_id=app.id,
            mode=app.mode,
            humanize=humanize,
            resume=resume,
            listing=JobListingPayload(
                id=listing.id,
                title=listing.title,
                company=listing.company,
                apply_url=listing.apply_url,
                canonical_url=listing.canonical_url,
                location=listing.location,
            ),
            intervention_wait_minutes=get_settings().intervention_wait_minutes,
        )
    )


def _owned_running_app(db: Session, user: User, application_id: int) -> Application:
    app = db.get(Application, application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


class FieldIn(BaseModel):
    label: str
    field_type: str = "text"
    options: list[str] = Field(default_factory=list)
    required: bool = False
    name: str | None = None
    surrounding_text: str = ""
    ref: str | None = None  # extension-side element reference, echoed back


class ResolutionOut(BaseModel):
    ref: str | None
    label: str
    status: str
    value: Any | None = None
    formatted: str | None = None
    kind: str = "text"
    source: str = "none"
    confidence: float = 0.0
    field_key: str | None = None
    is_knockout: bool = False
    is_eeo: bool = False
    auto_check: bool = False
    reason: str = ""
    draft: str | None = None
    file_url: str | None = None
    file_name: str | None = None


class ResolveRequest(BaseModel):
    fields: list[FieldIn]


class ResolveResponse(BaseModel):
    resolutions: list[ResolutionOut]
    run_active: bool


@router.post("/applications/{application_id}/resolve", response_model=ResolveResponse)
def resolve_fields(
    application_id: int,
    payload: ResolveRequest,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> ResolveResponse:
    from app.models import StoredFile
    from app.services.resolver import load_user_data

    app = _owned_running_app(db, user, application_id)
    listing = db.get(JobListing, app.listing_id)
    data = load_user_data(db, user)
    resolutions: list[ResolutionOut] = []
    for field_in in payload.fields:
        resolution = resolve_field(
            db,
            user,
            ResolverField(
                label=field_in.label,
                field_type=field_in.field_type,
                options=field_in.options,
                required=field_in.required,
                name=field_in.name,
                surrounding_text=field_in.surrounding_text,
            ),
            listing=listing,
            data=data,
        )
        out = ResolutionOut(
            ref=field_in.ref,
            label=field_in.label,
            status=resolution.status,
            value=resolution.value,
            formatted=resolution.formatted,
            kind=resolution.kind,
            source=resolution.source,
            confidence=resolution.confidence,
            field_key=resolution.field_key,
            is_knockout=resolution.is_knockout,
            is_eeo=resolution.is_eeo,
            auto_check=resolution.auto_check,
            reason=resolution.reason,
            draft=resolution.draft,
        )
        if resolution.status == "resolved" and resolution.kind == "file":
            file_row = db.get(StoredFile, int(resolution.value))
            if file_row is not None and file_row.user_id == user.id:
                out.file_url = f"/api/ext/files/{file_row.id}/download"
                out.file_name = file_row.filename
        if resolution.saved_answer_id and resolution.status == "resolved":
            mark_answer_used(db, resolution.saved_answer_id, listing)
        resolutions.append(out)
    record_event(
        db, app, "fields.resolved",
        {
            "total": len(resolutions),
            "resolved": sum(1 for r in resolutions if r.status == "resolved"),
            "needs_human": sum(1 for r in resolutions if r.status in ("needs_human", "draft_pending")),
        },
    )
    batch = db.get(RunBatch, app.run_batch_id) if app.run_batch_id else None
    return ResolveResponse(
        resolutions=resolutions, run_active=batch is None or batch.status == "running"
    )


@router.get("/files/{file_id}/download")
def ext_download_file(
    file_id: int,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
):
    """Device-token variant of the file download (for resume uploads)."""
    from fastapi.responses import FileResponse

    from app.models import StoredFile
    from app.services.storage import resolve_user_path

    row = db.get(StoredFile, file_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    path = resolve_user_path(user.id, row.path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File data missing")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)


class ExtInterventionIn(BaseModel):
    kind: str = Field(pattern="^(unknown_field|challenge|review|draft_approval|error)$")
    question: str | None = None
    field_meta: dict[str, Any] = Field(default_factory=dict)
    screenshot_b64: str | None = None


class ExtInterventionsRequest(BaseModel):
    items: list[ExtInterventionIn] = Field(min_length=1)
    reason: str = "unknown_field"


class ExtInterventionsResponse(BaseModel):
    intervention_ids: list[int]


@router.post(
    "/applications/{application_id}/interventions", response_model=ExtInterventionsResponse
)
def ext_create_interventions(
    application_id: int,
    payload: ExtInterventionsRequest,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> ExtInterventionsResponse:
    app = _owned_running_app(db, user, application_id)
    ids = []
    for item in payload.items:
        row = create_intervention(
            db,
            user,
            app,
            item.kind,
            question=item.question,
            field_meta=item.field_meta,
            screenshot_b64=item.screenshot_b64,
        )
        ids.append(row.id)
    if app.status == "filling":
        transition(db, app, "needs_human", reason=payload.reason, actor="extension")
    return ExtInterventionsResponse(intervention_ids=ids)


class InterventionStateOut(BaseModel):
    id: int
    kind: str
    status: str
    answer: Any | None
    field_meta: dict[str, Any]


@router.get(
    "/applications/{application_id}/interventions",
    response_model=list[InterventionStateOut],
)
def ext_list_interventions(
    application_id: int,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> list[InterventionStateOut]:
    app = _owned_running_app(db, user, application_id)
    rows = db.scalars(
        select(Intervention).where(Intervention.application_id == app.id).order_by(Intervention.id)
    )
    return [
        InterventionStateOut(
            id=r.id, kind=r.kind, status=r.status, answer=r.answer, field_meta=r.field_meta or {}
        )
        for r in rows
    ]


class ExtStatusRequest(BaseModel):
    status: str = Field(pattern="^(filling|needs_human|drafted|failed|stopped)$")
    reason: str | None = None
    error: str | None = None


@router.post("/applications/{application_id}/status", response_model=OkResponse)
def ext_set_status(
    application_id: int,
    payload: ExtStatusRequest,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    app = _owned_running_app(db, user, application_id)
    if payload.error:
        app.error = payload.error[:2000]
    try:
        transition(
            db, app, payload.status, reason=payload.reason or payload.status, actor="extension"
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return OkResponse()


class SubmitResultRequest(BaseModel):
    confirmed: bool
    field_snapshot: dict[str, Any] = Field(default_factory=dict)
    screenshot_b64: str | None = None


@router.post("/applications/{application_id}/submit-result", response_model=OkResponse)
def ext_submit_result(
    application_id: int,
    payload: SubmitResultRequest,
    device: Device = Depends(get_device),
    user: User = Depends(get_device_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    import base64 as b64mod

    from app.models import StoredFile

    app = _owned_running_app(db, user, application_id)
    if app.status not in ("filling", "needs_human"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is {app.status}")
    if app.status == "needs_human":
        transition(db, app, "filling", reason="resuming to record submission", actor="extension")
    transition(db, app, "submitting", actor="extension")
    app.field_snapshot = payload.field_snapshot
    if payload.screenshot_b64:
        try:
            data = b64mod.b64decode(payload.screenshot_b64)
        except Exception:
            data = b""
        if data:
            path = store_bytes(user.id, "screenshots", "confirmation.png", data)
            app.confirmation_screenshot_path = path
            db.add(
                StoredFile(
                    user_id=user.id,
                    kind="screenshot",
                    filename="confirmation.png",
                    content_type="image/png",
                    size_bytes=len(data),
                    path=path,
                )
            )
    transition(
        db,
        app,
        "submitted" if payload.confirmed else "submitted_unconfirmed",
        reason=None if payload.confirmed else "confirmation page not clearly detected",
        actor="extension",
    )
    return OkResponse()
