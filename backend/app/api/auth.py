from __future__ import annotations

import datetime as dt
import io

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import SESSION_COOKIE, get_current_user, get_session_record
from app.logging_conf import get_logger
from app.models import Profile, User, UserSession, utcnow
from app.schemas.auth import (
    ChangePasswordRequest,
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    OkResponse,
    RegisterRequest,
    SessionOut,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserOut,
    UserSettings,
)
from app.security import (
    hash_password,
    hash_token,
    new_token,
    new_totp_secret,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.services.rate_limit import login_limiter

log = get_logger(__name__)
router = APIRouter()


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookies_secure,
        path="/",
    )


def _create_session(
    db: Session, user: User, request: Request, totp_pending: bool
) -> tuple[UserSession, str]:
    token = new_token()
    record = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_token(16),
        created_at=utcnow(),
        expires_at=utcnow() + dt.timedelta(days=get_settings().session_ttl_days),
        ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
        totp_pending=totp_pending,
    )
    db.add(record)
    db.flush()
    return record, token


@router.post("/register", status_code=201, response_model=UserOut)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        settings=UserSettings().model_dump(),
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, email=email))
    log.info("auth.registered", user_id=user.id)
    return user


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResponse:
    key = f"{_client_ip(request)}:{payload.email.lower()}"
    if not login_limiter.allow(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts; wait a minute")
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    login_limiter.reset(key)

    if user.totp_enabled:
        record, token = _create_session(db, user, request, totp_pending=True)
        _set_session_cookie(response, token)
        return LoginResponse(requires_totp=True)

    record, token = _create_session(db, user, request, totp_pending=False)
    _set_session_cookie(response, token)
    return LoginResponse(csrf_token=record.csrf_token, user=UserOut.model_validate(user))


@router.post("/totp", response_model=LoginResponse)
def totp_step(
    payload: TotpVerifyRequest, request: Request, db: Session = Depends(get_db)
) -> LoginResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No pending login")
    record = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if record is None or record.revoked or not record.totp_pending:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No pending login")
    user = db.get(User, record.user_id)
    if user is None or not user.totp_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No pending login")
    if not login_limiter.allow(f"totp:{user.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts; wait a minute")
    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    record.totp_pending = False
    return LoginResponse(csrf_token=record.csrf_token, user=UserOut.model_validate(user))


@router.post("/logout", response_model=OkResponse)
def logout(
    response: Response,
    record: UserSession = Depends(get_session_record),
    db: Session = Depends(get_db),
) -> OkResponse:
    record.revoked = True
    response.delete_cookie(SESSION_COOKIE, path="/")
    return OkResponse()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/csrf", response_model=CsrfResponse)
def csrf(record: UserSession = Depends(get_session_record)) -> CsrfResponse:
    return CsrfResponse(csrf_token=record.csrf_token)


@router.post("/change-password", response_model=OkResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    record: UserSession = Depends(get_session_record),
    db: Session = Depends(get_db),
) -> OkResponse:
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    for other in db.scalars(select(UserSession).where(UserSession.user_id == user.id)):
        if other.id != record.id:
            other.revoked = True
    return OkResponse()


# --- Sessions ---------------------------------------------------------------


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    record: UserSession = Depends(get_session_record), db: Session = Depends(get_db)
) -> list[SessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == record.user_id, UserSession.revoked.is_(False))
        .order_by(UserSession.created_at.desc())
    ).all()
    return [
        SessionOut(
            id=r.id,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            ip=r.ip,
            user_agent=r.user_agent,
            current=r.id == record.id,
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", response_model=OkResponse)
def revoke_session(
    session_id: int,
    record: UserSession = Depends(get_session_record),
    db: Session = Depends(get_db),
) -> OkResponse:
    target = db.get(UserSession, session_id)
    if target is None or target.user_id != record.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    target.revoked = True
    return OkResponse()


# --- TOTP -------------------------------------------------------------------


@router.post("/totp/setup", response_model=TotpSetupResponse)
def totp_setup(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TotpSetupResponse:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP already enabled")
    secret = new_totp_secret()
    user.totp_secret = secret  # armed only after /totp/enable verifies a code
    uri = totp_provisioning_uri(secret, user.email)
    buf = io.BytesIO()
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    return TotpSetupResponse(secret=secret, provisioning_uri=uri, qr_svg=buf.getvalue().decode())


@router.post("/totp/enable", response_model=OkResponse)
def totp_enable(
    payload: TotpVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    if not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run /totp/setup first")
    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")
    user.totp_enabled = True
    return OkResponse()


@router.post("/totp/disable", response_model=OkResponse)
def totp_disable(
    payload: TotpVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP is not enabled")
    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid code")
    user.totp_enabled = False
    user.totp_secret = None
    return OkResponse()


# --- Settings ---------------------------------------------------------------


@router.get("/settings", response_model=UserSettings)
def get_user_settings(user: User = Depends(get_current_user)) -> UserSettings:
    return UserSettings.model_validate({**UserSettings().model_dump(), **(user.settings or {})})


@router.put("/settings", response_model=UserSettings)
def put_user_settings(
    payload: UserSettings, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> UserSettings:
    user.settings = payload.model_dump()
    return payload


@router.delete("/account", response_model=OkResponse)
def delete_account(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Delete the account and every row and file belonging to it."""
    from app.services.storage import delete_user_files

    delete_user_files(user.id)
    db.delete(user)  # DB rows cascade via FK ondelete
    response.delete_cookie(SESSION_COOKIE, path="/")
    log.info("auth.account_deleted", user_id=user.id)
    return OkResponse()
