"""Settings the user manages from the UI: AI provider credentials/model.

The API key is stored encrypted (services/crypto.py) and is NEVER returned
in plaintext — reads expose only a masked hint plus where the effective key
came from (the user's own setting, the environment, or nothing).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm.client import get_llm, reset_clients
from app.llm.config import config_for_user, env_config
from app.logging_conf import get_logger
from app.models import User
from app.schemas.auth import OkResponse
from app.services.crypto import decrypt_secret, encrypt_secret, mask_secret

log = get_logger(__name__)
router = APIRouter()

# Models offered in the picker. Opus 5 is the default and the strongest for
# résumé parsing and field mapping; Sonnet 5 and Haiku 4.5 are cheaper and
# faster if you run large searches.
AVAILABLE_MODELS: list[dict[str, str]] = [
    {
        "id": "claude-opus-5",
        "label": "Claude Opus 5",
        "note": "Recommended — best parsing and field-mapping accuracy",
    },
    {
        "id": "claude-sonnet-5",
        "label": "Claude Sonnet 5",
        "note": "Faster and cheaper; very capable for most listings",
    },
    {
        "id": "claude-haiku-4-5",
        "label": "Claude Haiku 4.5",
        "note": "Cheapest and fastest; best for high-volume searching",
    },
    {
        "id": "claude-opus-4-8",
        "label": "Claude Opus 4.8",
        "note": "Previous-generation Opus",
    },
]


class AISettingsOut(BaseModel):
    provider: str = "anthropic"
    # Never the key itself — only a hint like "sk-ant-…4f2a".
    key_hint: str | None = None
    key_source: str  # "user" | "env" | "none"
    key_editable: bool = True
    model: str
    offline: bool
    effective_offline: bool
    env_key_present: bool
    env_offline: bool
    available_models: list[dict[str, str]] = Field(default_factory=lambda: AVAILABLE_MODELS)


def _to_out(user: User) -> AISettingsOut:
    cfg = config_for_user(user)
    env = env_config()
    user_key = decrypt_secret(user.llm_api_key_enc)
    return AISettingsOut(
        key_hint=mask_secret(user_key) if user_key else mask_secret(env.api_key),
        key_source=cfg.key_source,
        model=cfg.model,
        offline=bool(user.llm_offline) if user.llm_offline is not None else env.offline,
        effective_offline=cfg.dry_run,
        env_key_present=bool(env.api_key),
        env_offline=env.offline,
    )


@router.get("/ai", response_model=AISettingsOut)
def get_ai_settings(user: User = Depends(get_current_user)) -> AISettingsOut:
    return _to_out(user)


class AISettingsUpdate(BaseModel):
    # Omit to leave the stored key unchanged; empty string clears it.
    api_key: str | None = Field(default=None, max_length=400)
    model: str | None = None
    offline: bool | None = None


@router.put("/ai", response_model=AISettingsOut)
def update_ai_settings(
    payload: AISettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AISettingsOut:
    if payload.api_key is not None:
        key = payload.api_key.strip()
        user.llm_api_key_enc = encrypt_secret(key) if key else None
    if payload.model is not None:
        user.llm_model = payload.model.strip() or None
    if payload.offline is not None:
        user.llm_offline = payload.offline
    db.flush()
    reset_clients()  # so the next call picks up the new credentials
    log.info(
        "settings.ai_updated",
        user_id=user.id,
        key_set=user.llm_api_key_enc is not None,
        model=user.llm_model,
        offline=user.llm_offline,
    )
    return _to_out(user)


@router.delete("/ai/key", response_model=AISettingsOut)
def clear_ai_key(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AISettingsOut:
    user.llm_api_key_enc = None
    db.flush()
    reset_clients()
    return _to_out(user)


class AITestResult(BaseModel):
    ok: bool
    offline: bool
    model: str
    key_source: str
    detail: str


@router.post("/ai/test", response_model=AITestResult)
def test_ai_connection(user: User = Depends(get_current_user)) -> AITestResult:
    """Make one tiny real call to verify the configured credentials work."""
    cfg = config_for_user(user)
    if cfg.dry_run:
        reason = (
            "Offline mode is on — nothing is sent to Anthropic."
            if cfg.offline
            else "No API key configured, so JobPilot uses offline heuristics."
        )
        return AITestResult(
            ok=True, offline=True, model=cfg.model, key_source=cfg.key_source, detail=reason
        )

    from app.llm.schemas import KnockoutClassification

    client = get_llm(cfg)
    try:
        result = client.parse(
            system="You classify job-application questions. Reply with the schema only.",
            prompt="Question from a job application form:\nAre you legally authorized to work?",
            output_type=KnockoutClassification,
            max_tokens=256,
        )
    except Exception as exc:
        # Never echo the key back, even inside an error string.
        message = str(exc)
        if cfg.api_key:
            message = message.replace(cfg.api_key, "***")
        return AITestResult(
            ok=False,
            offline=False,
            model=cfg.model,
            key_source=cfg.key_source,
            detail=message[:400],
        )
    return AITestResult(
        ok=True,
        offline=False,
        model=cfg.model,
        key_source=cfg.key_source,
        detail=f"Connected. Test classification returned is_knockout={result.is_knockout}.",
    )


@router.get("/ai/health", response_model=OkResponse)
def ai_health(user: User = Depends(get_current_user)) -> OkResponse:
    return OkResponse()
