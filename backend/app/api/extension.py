"""Endpoints the browser extension talks to.

Pairing is the only unauthenticated call (it consumes a one-time code); all
others require the device token issued at pairing (Authorization: Bearer).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db
from app.deps import get_device, get_device_user
from app.logging_conf import get_logger
from app.models import Device, PairingCode, User, utcnow
from app.security import hash_token, new_token

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
