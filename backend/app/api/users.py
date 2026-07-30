"""Account management, for administrators.

Scope is deliberately narrow: who has an account, who is an administrator,
and password resets for people who have locked themselves out. An admin does
NOT gain access to anyone else's job data — profiles, listings, runs and
applications stay isolated by user_id at the query layer, exactly as
tests/test_isolation.py asserts. Managing accounts and reading their contents
are different powers, and this module only grants the first.

Every route here mutates or lists accounts, so all of them sit behind
require_admin, and the destructive ones additionally refuse to strand an
install without an administrator.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.logging_conf import get_logger
from app.models import Profile, User, UserSession, utcnow
from app.schemas.auth import (
    AdminCreateUserRequest,
    AdminSetPasswordRequest,
    AdminUpdateUserRequest,
    AdminUserOut,
    OkResponse,
    UserSettings,
)
from app.security import hash_password

log = get_logger(__name__)
router = APIRouter()


def _admin_count(db: Session) -> int:
    return int(
        db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))) or 0
    )


def _load_target(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return target


def _revoke_sessions(db: Session, user_id: int) -> None:
    for record in db.scalars(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
    ):
        record.revoked = True


def _to_out(db: Session, user: User, *, me: User) -> AdminUserOut:
    rows = db.execute(
        select(func.count(), func.max(UserSession.last_seen_at)).where(
            UserSession.user_id == user.id,
            UserSession.revoked.is_(False),
            UserSession.expires_at > utcnow(),
        )
    ).one()
    return AdminUserOut(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        totp_enabled=user.totp_enabled,
        created_at=user.created_at,
        last_seen_at=rows[1],
        active_sessions=int(rows[0] or 0),
        is_self=user.id == me.id,
    )


@router.get("", response_model=list[AdminUserOut])
def list_users(
    me: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[AdminUserOut]:
    users = db.scalars(select(User).order_by(User.id.asc())).all()
    return [_to_out(db, u, me=me) for u in users]


@router.post("", status_code=201, response_model=AdminUserOut)
def create_user(
    payload: AdminCreateUserRequest,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        settings=UserSettings().model_dump(),
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.flush()
    # Same shape a self-registration produces, so the new account opens on a
    # profile page that works rather than a 404.
    db.add(Profile(user_id=user.id, email=email))
    log.info("admin.user_created", actor_id=me.id, user_id=user.id, is_admin=user.is_admin)
    return _to_out(db, user, me=me)


@router.patch("/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUpdateUserRequest,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    target = _load_target(db, user_id)
    # Removing the last administrator leaves an install nobody can manage, and
    # the only way back is a database shell. Refuse, and say what to do first.
    if target.is_admin and not payload.is_admin and _admin_count(db) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the only administrator. Promote another account first.",
        )
    target.is_admin = payload.is_admin
    log.info("admin.user_role_changed", actor_id=me.id, user_id=target.id, is_admin=target.is_admin)
    return _to_out(db, target, me=me)


@router.post("/{user_id}/password", response_model=OkResponse)
def set_password(
    user_id: int,
    payload: AdminSetPasswordRequest,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Reset a password without knowing the old one — the point of an admin
    reset. Every existing session for that account is revoked, so a reset also
    ends any session an intruder is holding."""
    target = _load_target(db, user_id)
    target.password_hash = hash_password(payload.new_password)
    _revoke_sessions(db, target.id)
    log.info("admin.password_reset", actor_id=me.id, user_id=target.id)
    return OkResponse()


@router.delete("/{user_id}", response_model=OkResponse)
def delete_user(
    user_id: int,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Delete an account and everything belonging to it."""
    from app.services.storage import delete_user_files

    target = _load_target(db, user_id)
    if target.id == me.id:
        # Deleting the account you are signed in as needs the session torn
        # down with it; Settings -> Danger does that properly.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Use Settings → Danger zone to delete your own account.",
        )
    if target.is_admin and _admin_count(db) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the only administrator. Promote another account first.",
        )
    delete_user_files(target.id)
    db.delete(target)  # DB rows cascade via FK ondelete
    log.info("admin.user_deleted", actor_id=me.id, user_id=user_id)
    return OkResponse()
