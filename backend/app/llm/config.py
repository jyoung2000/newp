"""Resolving which LLM credentials/model a given request should use.

Precedence: the user's own settings (Settings → AI, stored encrypted) →
the ANTHROPIC_API_KEY environment variable → offline heuristics.

"Offline" is a first-class state, not a failure: with no key, or with the
offline toggle on, JobPilot uses the deterministic fakes in llm/fakes.py and
sends nothing to Anthropic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import get_settings
from app.services.crypto import decrypt_secret

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models import User


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None
    model: str
    offline: bool
    # Where the key came from, for the UI to explain itself honestly.
    key_source: str  # "user" | "env" | "none"

    @property
    def dry_run(self) -> bool:
        return self.offline or not self.api_key


def env_config() -> LLMConfig:
    settings = get_settings()
    key = settings.anthropic_api_key or None
    return LLMConfig(
        api_key=key,
        model=settings.llm_model,
        offline=settings.llm_dry_run,
        key_source="env" if key else "none",
    )


def config_for_user(user: User | None) -> LLMConfig:
    """The effective config for this user."""
    base = env_config()
    if user is None:
        return base

    user_key = decrypt_secret(user.llm_api_key_enc)
    api_key = user_key or base.api_key
    key_source = "user" if user_key else base.key_source

    # The user's offline toggle wins when set; otherwise the env default.
    offline = base.offline if user.llm_offline is None else bool(user.llm_offline)

    return LLMConfig(
        api_key=api_key,
        model=user.llm_model or base.model,
        offline=offline,
        key_source=key_source,
    )
