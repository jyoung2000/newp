from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class LoginResponse(BaseModel):
    requires_totp: bool = False
    csrf_token: str | None = None
    user: UserOut | None = None


class UserOut(BaseModel):
    id: int
    email: str
    totp_enabled: bool
    is_admin: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


# --- Account management (admin only) ----------------------------------------


class AdminUserOut(BaseModel):
    """A user as an administrator sees it. Deliberately about the account and
    nothing in it: no profile, no listings, no application history."""

    id: int
    email: str
    is_admin: bool
    totp_enabled: bool
    created_at: dt.datetime
    last_seen_at: dt.datetime | None = None
    active_sessions: int = 0
    # True for the administrator making the request, so a UI can keep them
    # from locking themselves out of their own account.
    is_self: bool = False


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    is_admin: bool = False


class AdminUpdateUserRequest(BaseModel):
    is_admin: bool


class AdminSetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10, max_length=200)


class SessionOut(BaseModel):
    id: int
    created_at: dt.datetime
    last_seen_at: dt.datetime | None
    ip: str | None
    user_agent: str | None
    current: bool = False


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_svg: str  # inline SVG data for the QR code


class NotificationSettings(BaseModel):
    email_enabled: bool = False
    email_address: str | None = None
    webhook_enabled: bool = False
    # Any HTTP endpoint that accepts a POST; ntfy.sh topics and
    # Slack/Telegram-compatible webhook URLs work as-is.
    webhook_url: str | None = None


class UserSettings(BaseModel):
    """User-scoped settings stored in users.settings (JSON)."""

    humanize_default: bool = True
    run_mode_default: Literal["auto", "review", "draft"] = "review"
    executor_default: Literal["extension", "playwright", "auto"] = "auto"
    resolver_confidence_threshold: float = Field(default=0.75, ge=0.5, le=1.0)
    notifications: NotificationSettings = NotificationSettings()
    timezone: str = "UTC"
    onboarding_dismissed: bool = False


class CsrfResponse(BaseModel):
    csrf_token: str


class OkResponse(BaseModel):
    ok: bool = True
