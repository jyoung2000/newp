"""The polite HTTP layer every job source goes through.

Guarantees, in code (see docs/SOURCES.md):
  * A truthful, identifying User-Agent naming the project and repository.
    Never a spoofed browser UA.
  * robots.txt respected on every generic fetch (cached per host).
    Documented, purpose-built APIs opt out explicitly with a stated basis.
  * Hard per-host rate limit: at most 1 request/second/host, configurable
    slower only (config validation refuses lower values).
  * Exponential backoff on transient errors; 401/403/429 and bot-block
    pages mark the source `blocked` — never retried with evasion.
  * A small TTL cache so repeated searches don't re-fetch.
"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app import __version__
from app.config import get_settings
from app.logging_conf import get_logger

log = get_logger(__name__)

REPO_URL = "https://github.com/jyoung2000/newp"

BOT_BLOCK_MARKERS = (
    "verify you are human",
    "unusual activity",
    "security check",
    "just a moment",
    "attention required",
    "access denied",
    "request blocked",
    "are you a robot",
)


class SourceBlockedError(RuntimeError):
    """Raised when a host answered 401/403/429 or served a bot-block page.
    The caller marks the source blocked and backs off; nothing retries."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"{host}: {reason}")
        self.host = host
        self.reason = reason


class RobotsDisallowedError(RuntimeError):
    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows fetching {url}")
        self.url = url


@dataclass
class CachedResponse:
    expires_at: float
    status_code: int
    text: str
    json_data: Any | None


def user_agent() -> str:
    settings = get_settings()
    ua = f"JobPilot/{__version__} (+{REPO_URL}) self-hosted job-search assistant"
    if settings.user_agent_extra:
        ua += f" ({settings.user_agent_extra})"
    return ua


class PoliteHttpClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.min_interval = max(1.0, settings.min_host_interval_seconds)
        self.cache_ttl = settings.source_cache_ttl_seconds
        self._client = httpx.Client(
            headers={"User-Agent": user_agent()},
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
        )
        self._lock = threading.Lock()
        self._last_request_at: dict[str, float] = {}
        self._robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
        self._cache: dict[str, CachedResponse] = {}

    # --- politeness internals -------------------------------------------

    def _wait_for_host_slot(self, host: str) -> None:
        while True:
            with self._lock:
                last = self._last_request_at.get(host, 0.0)
                now = time.monotonic()
                wait = self.min_interval - (now - last)
                if wait <= 0:
                    self._last_request_at[host] = now
                    return
            time.sleep(min(wait, self.min_interval))

    def _robots_allows(self, url: str) -> bool:
        host = urlparse(url).netloc
        scheme = urlparse(url).scheme or "https"
        with self._lock:
            entry = self._robots.get(host)
        if entry is None or entry[0] < time.monotonic():
            parser: urllib.robotparser.RobotFileParser | None = None
            robots_url = f"{scheme}://{host}/robots.txt"
            try:
                self._wait_for_host_slot(host)
                response = self._client.get(robots_url)
                if response.status_code == 200:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(response.text.splitlines())
                # 4xx/5xx robots -> no restrictions stated -> allowed.
            except httpx.HTTPError:
                parser = None
            with self._lock:
                self._robots[host] = (time.monotonic() + 3600, parser)
            entry = (0.0, parser)
        parser = entry[1]
        if parser is None:
            return True
        return parser.can_fetch(user_agent(), url)

    def _looks_bot_blocked(self, response: httpx.Response) -> bool:
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type:
            return False
        sample = response.text[:4000].lower()
        return any(marker in sample for marker in BOT_BLOCK_MARKERS)

    # --- public API ------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        respect_robots: bool = True,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        max_retries: int = 2,
    ) -> httpx.Response:
        cache_key = url + ("?" + str(sorted(params.items())) if params else "")
        if use_cache:
            with self._lock:
                cached = self._cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                request = self._client.build_request("GET", url, params=params)
                response = httpx.Response(
                    cached.status_code, text=cached.text, request=request
                )
                return response

        if respect_robots and not self._robots_allows(url):
            raise RobotsDisallowedError(url)

        host = urlparse(url).netloc
        attempt = 0
        while True:
            self._wait_for_host_slot(host)
            try:
                response = self._client.get(url, params=params, headers=headers)
            except httpx.HTTPError:
                if attempt < max_retries:
                    attempt += 1
                    time.sleep(min(2**attempt, 8))
                    continue
                raise

            if response.status_code in (401, 403, 429):
                raise SourceBlockedError(host, f"HTTP {response.status_code}")
            if response.status_code >= 500 and attempt < max_retries:
                attempt += 1
                time.sleep(min(2**attempt, 8))
                continue
            if self._looks_bot_blocked(response):
                raise SourceBlockedError(host, "bot-block interstitial detected")
            break

        if use_cache and response.status_code == 200:
            with self._lock:
                self._cache[cache_key] = CachedResponse(
                    expires_at=time.monotonic() + self.cache_ttl,
                    status_code=response.status_code,
                    text=response.text,
                    json_data=None,
                )
                if len(self._cache) > 500:
                    now = time.monotonic()
                    self._cache = {
                        k: v for k, v in self._cache.items() if v.expires_at > now
                    }
        return response

    def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        host = urlparse(url).netloc
        self._wait_for_host_slot(host)
        response = self._client.post(url, json=json, headers=headers)
        if response.status_code in (401, 403, 429):
            raise SourceBlockedError(host, f"HTTP {response.status_code}")
        return response


_client: PoliteHttpClient | None = None
_client_lock = threading.Lock()


def get_http() -> PoliteHttpClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = PoliteHttpClient()
        return _client


def reset_http() -> None:
    """Testing hook."""
    global _client
    with _client_lock:
        _client = None
