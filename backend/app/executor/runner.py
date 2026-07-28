"""The Playwright queue runner.

Picks up queued applications assigned to the `playwright` executor (or
unassigned when no extension is paired), drives them through the shared
resolver and state machine, enforces the throughput ceilings, and hands
challenges + unknown fields to the human. A stopped or paused run leaves no
half-submitted forms.

This runs inside the arq worker. It is written so its orchestration logic can
be unit-tested with a fake session (no real browser); the Playwright session
is only constructed in `process_application` when a real fill happens.
"""
from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.executor.playwright_executor import ChallengeDetected, PlaywrightSession
from app.executor.states import transition
from app.logging_conf import get_logger
from app.models import Application, Intervention, JobListing, RunBatch, User, utcnow
from app.services.intervention_service import create_intervention
from app.services.pacing import check_submission_allowance
from app.services.resolver import (
    DetectedField,
    UserData,
    load_user_data,
    mark_answer_used,
    resolve_field,
)
from app.services.storage import resolve_user_path, store_bytes

log = get_logger(__name__)


def _run_is_active(db: Session, app: Application) -> bool:
    if app.run_batch_id is None:
        return True
    batch = db.get(RunBatch, app.run_batch_id)
    return batch is not None and batch.status == "running"


def claim_next_playwright_job(db: Session, user_id: int) -> Application | None:
    running = select(RunBatch.id).where(
        RunBatch.user_id == user_id, RunBatch.status == "running"
    )
    return db.scalar(
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.status == "queued",
            Application.run_batch_id.in_(running),
            or_(Application.executor == "playwright", Application.executor.is_(None)),
        )
        .order_by(Application.id)
    )


def resumable_playwright_job(db: Session, user_id: int) -> Application | None:
    """A parked needs_human app whose interventions are all resolved."""
    running = select(RunBatch.id).where(
        RunBatch.user_id == user_id, RunBatch.status == "running"
    )
    open_apps = select(Intervention.application_id).where(Intervention.status == "open")
    return db.scalar(
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.status == "needs_human",
            Application.executor == "playwright",
            Application.run_batch_id.in_(running),
            Application.parked_at.is_(None),
            ~Application.id.in_(open_apps),
        )
        .order_by(Application.updated_at)
    )


def park_expired_interventions(db: Session) -> int:
    """Park applications whose intervention window has lapsed. The runner
    moves on to the next job; it never times out into an automatic attempt."""
    settings = get_settings()
    cutoff = utcnow() - dt.timedelta(minutes=settings.intervention_wait_minutes)
    parked = 0
    apps = db.scalars(
        select(Application).where(
            Application.status == "needs_human", Application.parked_at.is_(None)
        )
    )
    for app in apps:
        open_ivs = list(
            db.scalars(
                select(Intervention).where(
                    Intervention.application_id == app.id, Intervention.status == "open"
                )
            )
        )
        if not open_ivs:
            continue
        oldest = min(iv.created_at for iv in open_ivs)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=dt.UTC)
        if oldest < cutoff:
            app.parked_at = utcnow()
            from app.executor.states import record_event

            record_event(db, app, "parked", {"reason": "intervention window elapsed"})
            parked += 1
    db.flush()
    return parked


async def process_application(db: Session, user: User, app: Application) -> None:
    """Drive one application to a terminal or needs_human state with a real
    browser. Challenges and unknown fields become interventions."""
    listing = db.get(JobListing, app.listing_id)
    assert listing is not None
    apply_url = listing.apply_url or listing.canonical_url
    data = load_user_data(db, user)
    humanize = app.humanize if app.humanize is not None else True

    session = PlaywrightSession(humanize=humanize)
    try:
        await session.start()
        try:
            await session.goto(apply_url)
        except ChallengeDetected as challenge:
            await _raise_challenge(db, user, app, session, challenge)
            return

        outcome = await _fill_page(db, user, app, listing, data, session)
        if outcome == "needs_human":
            return
        if outcome == "stopped":
            transition(db, app, "stopped", reason="run stopped mid-fill", actor="system")
            return

        # Draft-only mode: screenshot, never submit.
        if app.mode == "draft":
            shot = await session.screenshot()
            path = store_bytes(user.id, "screenshots", "draft.png", shot)
            app.confirmation_screenshot_path = path
            transition(db, app, "drafted", reason="draft-only mode; not submitted", actor="system")
            return

        # Review mode is a human gate before submit; raise a review
        # intervention and stop here (resumed after approval).
        if app.mode == "review":
            shot = await session.screenshot()
            create_intervention(
                db, user, app, "review",
                question="Review the filled application before it is submitted",
                screenshot_bytes=shot,
            )
            transition(db, app, "needs_human", reason="review", actor="system")
            return

        # Auto mode: everything resolved confidently -> submit.
        await _submit(db, user, app, session)
    except ChallengeDetected as challenge:
        await _raise_challenge(db, user, app, session, challenge)
    except Exception as exc:  # pragma: no cover - browser/runtime failure
        app.error = str(exc)[:2000]
        transition(db, app, "failed", reason=str(exc)[:200], actor="system")
        log.exception("runner.application_failed", application_id=app.id)
    finally:
        await session.close()


async def _fill_page(
    db: Session,
    user: User,
    app: Application,
    listing: JobListing,
    data: UserData,
    session: PlaywrightSession,
) -> str:
    fields = await session.discover_fields()
    unresolved: list[DetectedField] = []
    unresolved_meta: list[dict] = []

    for field in fields:
        if not _run_is_active(db, app):
            return "stopped"
        detected = DetectedField(
            label=field.label,
            field_type=field.field_type,
            options=field.options,
            required=field.required,
            name=field.name,
            surrounding_text=field.surrounding_text,
        )
        resolution = resolve_field(db, user, detected, listing=listing, data=data)
        if resolution.status == "resolved":
            try:
                await _apply_resolution(db, user, session, field, resolution)
                if resolution.saved_answer_id:
                    mark_answer_used(db, resolution.saved_answer_id, listing)
            except ChallengeDetected:
                raise
        elif resolution.status == "leave_blank":
            continue
        else:  # needs_human / draft_pending
            unresolved.append(detected)
            unresolved_meta.append(
                {
                    "label": field.label,
                    "field_type": field.field_type,
                    "options": field.options,
                    "required": field.required,
                    "reason": resolution.reason,
                    "is_knockout": resolution.is_knockout,
                    "is_eeo": resolution.is_eeo,
                    "draft": resolution.draft,
                }
            )

    if unresolved:
        shot = await session.screenshot()
        for meta in unresolved_meta:
            kind = "draft_approval" if meta.get("draft") else "unknown_field"
            create_intervention(
                db, user, app, kind,
                question=meta["label"],
                field_meta=meta,
                screenshot_bytes=shot,
                notify=meta is unresolved_meta[-1],  # one notification for the batch
            )
        transition(db, app, "needs_human", reason="unknown_field", actor="system")
        return "needs_human"
    return "ok"


async def _apply_resolution(db, user, session, field, resolution) -> None:
    if resolution.kind == "file" and resolution.value is not None:
        from app.models import StoredFile

        file_row = db.get(StoredFile, int(resolution.value))
        if file_row is not None and file_row.user_id == user.id:
            path = resolve_user_path(user.id, file_row.path)
            await session.upload_file(field.ref, str(path))
        return
    if resolution.auto_check:
        await session.set_checkbox(field.ref, True)
        return
    if field.field_type == "select":
        await session.select_option(field.ref, resolution.formatted or str(resolution.value))
    elif field.field_type == "radio":
        await session.choose_radio(field.name or field.ref, resolution.formatted or str(resolution.value))
    elif field.field_type == "checkbox":
        truthy = str(resolution.value).lower() in ("true", "yes", "1")
        await session.set_checkbox(field.ref, truthy)
    else:
        await session.fill_text(field.ref, resolution.formatted or str(resolution.value))


async def _submit(db: Session, user: User, app: Application, session: PlaywrightSession) -> None:
    if not _run_is_active(db, app):
        transition(db, app, "stopped", reason="run stopped before submit", actor="system")
        return
    pacing = check_submission_allowance(db, user.id)
    if not pacing.allowed:
        # Re-queue rather than submit past the ceiling.
        transition(db, app, "needs_human", reason="error", actor="system")
        create_intervention(
            db, user, app, "error",
            question=f"Paused: {pacing.reason}. Resume later or raise the limit.",
        )
        return
    transition(db, app, "submitting", actor="system")
    from app.executor.playwright_executor import ChallengeDetected

    assert session.page is not None
    try:
        await session.check_for_challenge(session.page.url)
        submit = session.page.get_by_role("button", name=lambda n: bool(n) and "submit" in n.lower())
        if await submit.count() == 0:
            submit = session.page.locator("button[type=submit], input[type=submit]")
        await submit.first.click()
        await session.page.wait_for_load_state("networkidle", timeout=30000)
    except ChallengeDetected:
        raise
    except Exception as exc:
        app.error = f"submit click failed: {exc}"
        transition(db, app, "failed", reason="submit failed", actor="system")
        return

    shot = await session.screenshot()
    path = store_bytes(user.id, "screenshots", "confirmation.png", shot)
    app.confirmation_screenshot_path = path
    app.field_snapshot = await _snapshot_fields(session)

    confirmed = await _looks_confirmed(session)
    transition(
        db, app,
        "submitted" if confirmed else "submitted_unconfirmed",
        reason=None if confirmed else "confirmation not clearly detected",
        actor="system",
    )


async def _snapshot_fields(session: PlaywrightSession) -> dict:
    assert session.page is not None
    try:
        return await session.page.evaluate(
            "() => { const o={}; for (const el of document.querySelectorAll('[data-jp-ref]'))"
            " { o[el.getAttribute('data-jp-ref')] = { name: el.name||null,"
            " value: (el.type==='password'?'***':(el.value||'')).slice(0,200) }; } return o; }"
        )
    except Exception:
        return {}


async def _looks_confirmed(session: PlaywrightSession) -> bool:
    assert session.page is not None
    try:
        text = (await session.page.inner_text("body"))[:5000].lower()
    except Exception:
        return False
    markers = ["thank you", "application received", "successfully submitted", "we received", "confirmation"]
    return any(m in text for m in markers)


async def _raise_challenge(
    db: Session, user: User, app: Application, session: PlaywrightSession, challenge: ChallengeDetected
) -> None:
    """Halt and hand the live page to a human via noVNC. No solving, ever."""
    shot = b""
    try:
        shot = await session.screenshot()
    except Exception:
        pass
    from app.executor.states import record_event

    record_event(db, app, "challenge.detected", {"detail": challenge.detail, "kind": challenge.kind})
    create_intervention(
        db, user, app, "challenge",
        question=(
            "A human-verification challenge appeared. Solve it yourself in the live "
            "browser (noVNC), then press Resume."
        ),
        field_meta={"detail": challenge.detail, "kind": challenge.kind, "novnc": get_settings().novnc_url},
        screenshot_bytes=shot or None,
    )
    transition(db, app, "needs_human", reason="challenge", actor="system")
    log.info("runner.challenge_routed_to_human", application_id=app.id, detail=challenge.detail)


def run_pending_for_user(user_id: int, max_jobs: int = 5) -> int:
    """Synchronous entrypoint used by the worker. Processes up to max_jobs
    applications for one user, honoring pacing and run state."""
    session_local = get_sessionmaker()
    processed = 0
    for _ in range(max_jobs):
        db = session_local()
        try:
            user = db.get(User, user_id)
            if user is None:
                return processed
            pacing = check_submission_allowance(db, user_id)
            app = resumable_playwright_job(db, user_id)
            if app is None and pacing.allowed:
                app = claim_next_playwright_job(db, user_id)
            if app is None:
                db.commit()
                return processed
            if app.status == "queued":
                transition(db, app, "filling", reason="claimed by worker", actor="system")
            elif app.status == "needs_human":
                transition(db, app, "filling", reason="resuming after interventions", actor="system")
            db.commit()
            asyncio.run(process_application(db, user, app))
            db.commit()
            processed += 1
        except Exception:  # pragma: no cover
            db.rollback()
            log.exception("runner.user_batch_failed", user_id=user_id)
            return processed
        finally:
            db.close()
    return processed
