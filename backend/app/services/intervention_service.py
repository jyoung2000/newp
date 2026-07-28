"""Interventions: every moment JobPilot stops and asks the human."""
from __future__ import annotations

import base64
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_conf import get_logger
from app.models import (
    Application,
    Intervention,
    JobListing,
    SavedAnswer,
    StoredFile,
    User,
    utcnow,
)
from app.services.normalize import normalize_question
from app.services.notify import notify_user, push_badge
from app.services.storage import store_bytes

log = get_logger(__name__)

KIND_TITLES = {
    "unknown_field": "A form question needs your answer",
    "challenge": "A human check needs you",
    "review": "An application is ready for your review",
    "draft_approval": "A drafted answer needs your approval",
    "error": "An application hit a problem",
}


def open_intervention_count(db: Session, user_id: int) -> int:
    return len(
        list(
            db.scalars(
                select(Intervention.id).where(
                    Intervention.user_id == user_id, Intervention.status == "open"
                )
            )
        )
    )


def create_intervention(
    db: Session,
    user: User,
    application: Application,
    kind: str,
    *,
    question: str | None = None,
    field_meta: dict[str, Any] | None = None,
    screenshot_bytes: bytes | None = None,
    screenshot_b64: str | None = None,
    notify: bool = True,
) -> Intervention:
    screenshot_path = None
    data = screenshot_bytes
    if data is None and screenshot_b64:
        try:
            data = base64.b64decode(screenshot_b64)
        except Exception:
            data = None
    if data:
        screenshot_path = store_bytes(user.id, "screenshots", f"intervention_{kind}.png", data)
        db.add(
            StoredFile(
                user_id=user.id,
                kind="screenshot",
                filename=f"intervention_{kind}.png",
                content_type="image/png",
                size_bytes=len(data),
                path=screenshot_path,
            )
        )
    row = Intervention(
        application_id=application.id,
        user_id=user.id,
        kind=kind,
        question=question,
        field_meta=field_meta or {},
        screenshot_path=screenshot_path,
    )
    db.add(row)
    db.flush()
    if notify:
        listing = db.get(JobListing, application.listing_id)
        title = KIND_TITLES.get(kind, "JobPilot needs you")
        where = f"{listing.title} at {listing.company}" if listing else "an application"
        notify_user(
            user,
            title,
            f"{question or kind} — {where}",
            {"intervention_id": row.id, "application_id": application.id, "kind": kind},
        )
        push_badge(user.id, open_intervention_count(db, user.id))
    log.info(
        "intervention.created",
        intervention_id=row.id,
        application_id=application.id,
        kind=kind,
    )
    return row


def answer_intervention(
    db: Session,
    user: User,
    intervention: Intervention,
    answer: Any,
    *,
    save_to_kb: bool = True,
    question_key_override: str | None = None,
    skip: bool = False,
) -> Intervention:
    intervention.status = "answered"
    intervention.answer = {"skip": True} if skip else answer
    intervention.resolved_by = "user"
    intervention.resolved_at = utcnow()
    intervention.saved_to_kb = False

    if save_to_kb and not skip and intervention.kind in ("unknown_field", "draft_approval"):
        question_text = intervention.question or str(
            (intervention.field_meta or {}).get("label", "")
        )
        if question_text:
            listing = None
            application = db.get(Application, intervention.application_id)
            if application is not None:
                listing = db.get(JobListing, application.listing_id)
            key = question_key_override or normalize_question(
                question_text,
                company=listing.company if listing else None,
                location=listing.location if listing else None,
            )
            existing = db.scalar(
                select(SavedAnswer).where(
                    SavedAnswer.user_id == user.id, SavedAnswer.question_key == key
                )
            )
            value = answer if not isinstance(answer, dict) else answer.get("value", answer)
            if existing is None:
                db.add(
                    SavedAnswer(
                        user_id=user.id,
                        question_key=key,
                        question_text=question_text,
                        answer=value,
                        answer_type=str((intervention.field_meta or {}).get("field_type", "text")),
                        source="intervention",
                        approved=True,
                        job_family=key if intervention.kind == "draft_approval" else None,
                    )
                )
            else:
                existing.answer = value
                existing.approved = True
            intervention.saved_to_kb = True
    db.flush()
    push_badge(user.id, open_intervention_count(db, user.id))
    # Wake whichever executor is waiting on this intervention.
    from app.ws import publish_sync

    publish_sync(
        user.id,
        {
            "type": "intervention.answered",
            "intervention_id": intervention.id,
            "application_id": intervention.application_id,
            "also_ext": True,
        },
    )
    return intervention


def expire_intervention(db: Session, intervention: Intervention) -> None:
    intervention.status = "expired"
    intervention.resolved_by = "timeout"
    intervention.resolved_at = utcnow()
    db.flush()
