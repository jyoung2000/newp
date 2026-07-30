from __future__ import annotations

import datetime as dt
import io

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Device, PairingCode, User, utcnow
from app.schemas.auth import OkResponse
from app.security import hash_token, new_pairing_code
from app.services.link_code import build_link_code

router = APIRouter()

PAIRING_TTL_MINUTES = 10


class PairingCodeOut(BaseModel):
    code: str
    qr_svg: str
    expires_at: dt.datetime
    app_url: str
    # One string to paste into the extension, carrying both halves of what
    # pairing needs. Asking someone to copy a 6-digit code AND retype the
    # server URL fails in the ordinary case: the URL that works is the one
    # they are browsing right now, not "localhost", and they have no way to
    # know that.
    link_code: str


class DeviceOut(BaseModel):
    id: int
    name: str
    browser: str | None
    created_at: dt.datetime
    last_seen_at: dt.datetime | None
    online: bool = False
    extension_version: str | None = None

    model_config = {"from_attributes": True}


@router.post("/pairing-code", response_model=PairingCodeOut)
def create_pairing_code(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> PairingCodeOut:
    # Invalidate any outstanding codes for this user first.
    for row in db.scalars(
        select(PairingCode).where(PairingCode.user_id == user.id, PairingCode.used.is_(False))
    ):
        row.used = True
    code = new_pairing_code()
    expires = utcnow() + dt.timedelta(minutes=PAIRING_TTL_MINUTES)
    db.add(
        PairingCode(
            user_id=user.id, code_hash=hash_token(code), created_at=utcnow(), expires_at=expires
        )
    )
    settings = get_settings()
    # request.base_url is the origin this browser actually reached the app on —
    # a LAN address, a hostname, a reverse-proxied domain, whatever works from
    # here. That is exactly the URL the extension needs, and the one nobody can
    # guess. PUBLIC_URL wins when set, since that is the deliberate answer.
    app_url = settings.public_url or str(request.base_url).rstrip("/")
    payload = f"{app_url}/#pair={code}"
    buf = io.BytesIO()
    qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    return PairingCodeOut(
        code=code,
        qr_svg=buf.getvalue().decode(),
        expires_at=expires,
        app_url=app_url,
        link_code=build_link_code(app_url, code),
    )


@router.get("", response_model=list[DeviceOut])
def list_devices(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DeviceOut]:
    from app.ws import hub

    online = set(hub.ext_devices_online(user.id))
    rows = db.scalars(
        select(Device)
        .where(Device.user_id == user.id, Device.revoked.is_(False))
        .order_by(Device.created_at.desc())
    ).all()
    out = []
    for row in rows:
        item = DeviceOut.model_validate(row)
        item.online = row.id in online
        out.append(item)
    return out


@router.delete("/{device_id}", response_model=OkResponse)
def revoke_device(
    device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    device.revoked = True
    return OkResponse()
