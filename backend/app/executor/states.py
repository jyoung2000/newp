"""Application state machine.

Every status change goes through `transition()`, which validates the move,
appends the audit event, and pushes a live update to the UI. Terminal
submission states can never be re-entered — one application per posting,
ever, and never a resubmission.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.logging_conf import get_logger
from app.models import Application, ApplicationEvent, utcnow
from app.ws import publish_sync

log = get_logger(__name__)

# from-status -> allowed to-statuses
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"queued", "skipped"},
    "queued": {"filling", "skipped", "stopped"},
    "filling": {"needs_human", "submitting", "drafted", "failed", "stopped"},
    "needs_human": {"filling", "skipped", "stopped", "failed"},
    "submitting": {"submitted", "submitted_unconfirmed", "failed"},
    "failed": {"queued", "skipped"},
    "skipped": {"queued"},
    "stopped": {"queued"},
    # Terminal: an application is never submitted twice, and a drafted
    # application is finished manually by the user.
    "submitted": set(),
    "submitted_unconfirmed": set(),
    "drafted": set(),
}

TERMINAL = {"submitted", "submitted_unconfirmed", "drafted"}


class InvalidTransitionError(RuntimeError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Illegal application transition {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


def record_event(
    db: Session, application: Application, event_type: str, payload: dict[str, Any] | None = None
) -> None:
    db.add(
        ApplicationEvent(
            application_id=application.id,
            type=event_type,
            payload=payload or {},
            created_at=utcnow(),
        )
    )


def transition(
    db: Session,
    application: Application,
    to_status: str,
    *,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "system",
) -> Application:
    from_status = application.status
    allowed = TRANSITIONS.get(from_status)
    if allowed is None or to_status not in allowed:
        raise InvalidTransitionError(from_status, to_status)

    application.status = to_status
    event_payload: dict[str, Any] = {"from": from_status, "to": to_status, "actor": actor}
    if reason:
        event_payload["reason"] = reason
    if payload:
        event_payload.update(payload)

    if to_status == "needs_human":
        application.needs_human_reason = reason
    elif from_status == "needs_human":
        application.needs_human_reason = None
        application.parked_at = None
    if to_status in ("submitted", "submitted_unconfirmed"):
        application.submitted_at = utcnow()
    if to_status == "queued":
        application.error = None

    record_event(db, application, f"status.{to_status}", event_payload)
    db.flush()
    publish_sync(
        application.user_id,
        {
            "type": "application.status",
            "application_id": application.id,
            "status": to_status,
            "reason": reason,
        },
    )
    log.info(
        "application.transition",
        application_id=application.id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
    )
    return application
