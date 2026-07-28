"""User notifications: live UI (WebSocket), extension badge, optional email
and webhook (ntfy/Slack/Telegram-compatible endpoints)."""
from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage
from typing import Any

import httpx

from app.config import get_settings
from app.logging_conf import get_logger
from app.models import User
from app.schemas.auth import UserSettings
from app.ws import publish_sync

log = get_logger(__name__)


def _user_settings(user: User) -> UserSettings:
    return UserSettings.model_validate({**UserSettings().model_dump(), **(user.settings or {})})


def notify_user(user: User, title: str, message: str, payload: dict[str, Any] | None = None) -> None:
    """Fire-and-forget on every configured channel at once."""
    publish_sync(
        user.id,
        {"type": "notification", "title": title, "message": message, **(payload or {})},
    )
    settings = _user_settings(user)
    if settings.notifications.webhook_enabled and settings.notifications.webhook_url:
        threading.Thread(
            target=_send_webhook,
            args=(settings.notifications.webhook_url, title, message),
            daemon=True,
        ).start()
    if settings.notifications.email_enabled:
        address = settings.notifications.email_address or user.email
        threading.Thread(
            target=_send_email, args=(address, title, message), daemon=True
        ).start()


def _send_webhook(url: str, title: str, message: str) -> None:
    try:
        if "ntfy" in url:
            # ntfy topics take plain text with a Title header.
            httpx.post(url, content=message, headers={"Title": title}, timeout=10)
        else:
            # Slack-compatible and generic JSON webhooks.
            httpx.post(url, json={"title": title, "text": f"{title}: {message}"}, timeout=10)
    except Exception as exc:
        log.warning("notify.webhook_failed", error=str(exc))


def _send_email(address: str, title: str, message: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        return
    try:
        email = EmailMessage()
        email["Subject"] = f"[JobPilot] {title}"
        email["From"] = settings.smtp_from or settings.smtp_username or "jobpilot@localhost"
        email["To"] = address
        email.set_content(message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(email)
    except Exception as exc:
        log.warning("notify.email_failed", error=str(exc))


def push_badge(user_id: int, open_interventions: int) -> None:
    """Extension badge count (delivered over the extension WebSocket)."""
    publish_sync(
        user_id,
        {"type": "badge", "open_interventions": open_interventions, "also_ext": True},
    )
