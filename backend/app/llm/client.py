"""The single place JobPilot talks to the Anthropic API.

Every call is a `messages.parse` structured-output request validated against
a Pydantic schema. When no key is configured — or the user turned on offline
mode — the client routes to deterministic offline fakes instead: same
signatures, same contract, nothing sent to Anthropic.
"""
from __future__ import annotations

from typing import Any, TypeVar, cast

from pydantic import BaseModel

from app.llm.config import LLMConfig, env_config
from app.logging_conf import get_logger

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when the model call fails after retries or is refused."""


class LLMClient:
    def __init__(self, api_key: str | None, model: str, dry_run: bool) -> None:
        self.model = model
        self.dry_run = dry_run or not api_key
        self._client = None
        if not self.dry_run:
            import anthropic

            # SDK retries 429/5xx/connection errors with exponential backoff.
            self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    @property
    def available(self) -> bool:
        return not self.dry_run

    def parse(
        self,
        *,
        system: str,
        prompt: str,
        output_type: type[T],
        max_tokens: int = 4096,
    ) -> T:
        """One structured-output call. Raises LLMError on refusal/failure."""
        assert self._client is not None, "parse() must not be called in dry-run mode"
        import anthropic

        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=output_type,
            )
        except anthropic.APIStatusError as exc:
            log.warning("llm.api_error", status=exc.status_code, task=output_type.__name__)
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request (stop_reason=refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("Model output was truncated (max_tokens); raise the limit")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("Model returned no parseable structured output")
        return parsed

    def read_image_text(
        self,
        *,
        image_b64: str,
        media_type: str = "image/png",
        instruction: str,
        max_tokens: int = 200,
    ) -> str:
        """Read the text in a small image crop. Used as the last resort for a
        form field whose label exists only as pixels — a canvas-rendered form,
        or an icon-only control with no name, label or placeholder.

        Deliberately narrow: it is handed a crop of one field, and it returns
        text. It never sees a whole page, and callers must check `available`
        first — in offline mode nothing leaves the machine and the field goes
        to the human instead."""
        assert self._client is not None, "read_image_text() must not be called in dry-run mode"
        import anthropic

        image_block: anthropic.types.ImageBlockParam = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": cast(Any, media_type),
                "data": image_b64,
            },
        }
        text_block: anthropic.types.TextBlockParam = {"type": "text", "text": instruction}
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": [image_block, text_block]}],
            )
        except anthropic.APIStatusError as exc:
            log.warning("llm.api_error", status=exc.status_code, task="read_image_text")
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request (stop_reason=refusal)")
        # Content blocks are a wide union; only text blocks carry a label.
        parts = [
            block.text for block in response.content if isinstance(block, anthropic.types.TextBlock)
        ]
        return " ".join(parts).strip()


# Clients are cached per distinct configuration so a user's own key doesn't
# leak across users and switching models doesn't rebuild on every call.
_clients: dict[tuple[str | None, str, bool], LLMClient] = {}


def get_llm(config: LLMConfig | None = None) -> LLMClient:
    cfg = config or env_config()
    key = (cfg.api_key, cfg.model, cfg.dry_run)
    client = _clients.get(key)
    if client is None:
        client = LLMClient(api_key=cfg.api_key, model=cfg.model, dry_run=cfg.dry_run)
        if len(_clients) > 32:  # bound the cache in multi-user installs
            _clients.clear()
        _clients[key] = client
        if client.dry_run:
            log.info("llm.offline_mode", reason="offline toggle" if cfg.offline else "no API key")
    return client


def reset_clients() -> None:
    """Testing/settings-change hook."""
    _clients.clear()
