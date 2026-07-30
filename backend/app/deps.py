"""FastAPI dependencies: session-cookie auth, device-token auth, CSRF.

Every data query downstream of these dependencies filters by the
authenticated user's id — user isolation is enforced at the query layer and
verified by tests/test_isolation.py.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Device, User, UserSession, utcnow
from app.security import hash_token

SESSION_COOKIE = "jobpilot_session"
CSRF_HEADER = "x-csrf-token"
# Methods that mutate state and therefore require the CSRF header on
# cookie-authenticated requests.
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _load_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    record = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if record is None or record.revoked or record.totp_pending:
        return None
    now = utcnow()
    expires = record.expires_at
    if expires.tzinfo is None:  # SQLite round-trips naive datetimes
        expires = expires.replace(tzinfo=dt.UTC)
    if expires < now:
        return None
    record.last_seen_at = now
    return record


def get_session_record(request: Request, db: Session = Depends(get_db)) -> UserSession:
    record = _load_session(db, request.cookies.get(SESSION_COOKIE))
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if request.method in UNSAFE_METHODS:
        header = request.headers.get(CSRF_HEADER)
        if not header or header != record.csrf_token:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    return record


def get_current_user(
    record: UserSession = Depends(get_session_record), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Gate for account management. 403, not 404 — the caller is authenticated,
    it just isn't an admin, and pretending the route doesn't exist would only
    make a legitimate permission problem harder to diagnose."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


def get_device(request: Request, db: Session = Depends(get_db)) -> Device:
    """Bearer device-token auth for the browser extension."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device token required")
    token = auth[7:].strip()
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(token)))
    if device is None or device.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device token invalid or revoked")
    device.last_seen_at = utcnow()
    return device


def get_device_user(device: Device = Depends(get_device), db: Session = Depends(get_db)) -> User:
    user = db.get(User, device.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device token invalid")
    return user


async def ws_user_from_cookie(websocket: WebSocket, db: Session) -> User | None:
    record = _load_session(db, websocket.cookies.get(SESSION_COOKIE))
    if record is None:
        return None
    return db.get(User, record.user_id)


async def ws_device_from_token(websocket: WebSocket, db: Session, token: str) -> Device | None:
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(token)))
    if device is None or device.revoked:
        return None
    device.last_seen_at = utcnow()
    return device
