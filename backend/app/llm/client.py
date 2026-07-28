"""The single place JobPilot talks to the Anthropic API.

Every call is a `messages.parse` structured-output request validated against
a Pydantic schema. With LLM_DRY_RUN=1 (tests, keyless demos) the client
routes to deterministic offline fakes instead — same signatures, same
contract.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings
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


@lru_cache
def get_llm() -> LLMClient:
    settings = get_settings()
    client = LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        dry_run=settings.llm_dry_run,
    )
    if client.dry_run:
        log.info("llm.dry_run_mode", reason="LLM_DRY_RUN set" if settings.llm_dry_run else "no API key")
    return client
