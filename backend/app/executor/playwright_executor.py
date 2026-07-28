"""Server-side executor: Playwright Chromium, headful under Xvfb so a human
can take over the live page via noVNC when a challenge appears.

Best suited to straightforward Greenhouse/Lever/Ashby forms and to running
while the user's browser is closed. It shares the resolver and state machine
with the extension executor, and it obeys the same hard rules:
  * On any challenge or login wall it halts all input immediately and routes
    to a human — it never solves, and it re-verifies the challenge is gone
    before resuming.
  * Humanized input fires the full native event chain; instant mode still
    dispatches real events.
  * Throughput ceilings and the run stop-flag are checked at every step.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.executor.captcha import DETECTION_JS, is_login_url
from app.executor.humanize import TimingProfile, profile_for
from app.logging_conf import get_logger

log = get_logger(__name__)


class ChallengeDetected(Exception):
    def __init__(self, detail: str, kind: str = "challenge") -> None:
        super().__init__(detail)
        self.detail = detail
        self.kind = kind


@dataclass
class DetectedFormField:
    ref: str
    label: str
    field_type: str
    options: list[str]
    required: bool
    name: str | None
    surrounding_text: str


# Field discovery script. Read-only: it inspects the DOM and returns field
# descriptors; it never fills or clicks.
DISCOVER_JS = r"""
() => {
  const fields = [];
  let counter = 0;
  const labelFor = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) {
      const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lab) return lab.innerText.trim();
    }
    const wrapLabel = el.closest('label');
    if (wrapLabel) return wrapLabel.innerText.trim();
    const group = el.closest('fieldset');
    if (group) {
      const legend = group.querySelector('legend');
      if (legend) return legend.innerText.trim();
    }
    if (el.placeholder) return el.placeholder;
    if (el.name) return el.name;
    return '';
  };
  const surrounding = (el) => {
    const container = el.closest('div, fieldset, section, li') || el.parentElement;
    return container ? container.innerText.slice(0, 400) : '';
  };
  const controls = document.querySelectorAll(
    'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select'
  );
  const radioGroups = {};
  for (const el of controls) {
    if (el.disabled || el.offsetParent === null) continue;
    const ref = 'jp-' + (counter++);
    el.setAttribute('data-jp-ref', ref);
    let type = (el.tagName === 'TEXTAREA') ? 'textarea'
             : (el.tagName === 'SELECT') ? 'select'
             : (el.type || 'text');
    let options = [];
    if (type === 'select') {
      options = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
    }
    if (type === 'radio' || type === 'checkbox') {
      const name = el.name || ref;
      if (type === 'radio') {
        if (radioGroups[name]) {
          radioGroups[name].options.push(el.value || el.getAttribute('aria-label') || '');
          continue;
        }
        radioGroups[name] = { ref, options: [el.value || ''] };
      }
    }
    fields.push({
      ref, label: labelFor(el), field_type: type,
      options, required: el.required || el.getAttribute('aria-required') === 'true',
      name: el.name || null, surrounding_text: surrounding(el),
    });
  }
  for (const name in radioGroups) {
    const g = radioGroups[name];
    const f = fields.find(x => x.ref === g.ref);
    if (f) { f.field_type = 'radio'; f.options = g.options.filter(Boolean); }
  }
  return fields;
}
"""


class PlaywrightSession:
    """Thin async wrapper around a headful Chromium page with the JobPilot
    behaviors baked in. Kept import-light so the rest of the app (and the
    tests) don't require Playwright to be installed."""

    def __init__(self, humanize: bool) -> None:
        self.profile: TimingProfile = profile_for(humanize)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.page: Any = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        from app.config import get_settings

        settings = get_settings()
        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": not settings.playwright_headful}
        if settings.playwright_chromium_path:
            launch_kwargs["executable_path"] = settings.playwright_chromium_path
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        # A truthful, identifying UA — no browser spoofing (see README §3).
        from app.sources.http import user_agent

        self._context = await self._browser.new_context(
            user_agent=user_agent(), viewport={"width": 1280, "height": 900}
        )
        self.page = await self._context.new_page()

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    pass
        if self._playwright is not None:
            await self._playwright.stop()

    async def goto(self, url: str) -> None:
        assert self.page is not None
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self.check_for_challenge(previous_url=None)

    async def check_for_challenge(self, previous_url: str | None) -> None:
        """Raise ChallengeDetected if a challenge or login wall is present.
        Called continuously during any fill."""
        assert self.page is not None
        if is_login_url(self.page.url, previous_url):
            raise ChallengeDetected(f"redirected to login: {self.page.url}", kind="login")
        try:
            result = await self.page.evaluate(DETECTION_JS)
        except Exception:
            return
        if result and result.get("detected"):
            raise ChallengeDetected(result.get("detail", "challenge element"), kind="challenge")

    async def discover_fields(self) -> list[DetectedFormField]:
        assert self.page is not None
        raw = await self.page.evaluate(DISCOVER_JS)
        return [
            DetectedFormField(
                ref=f["ref"],
                label=f.get("label") or "",
                field_type=f.get("field_type") or "text",
                options=f.get("options") or [],
                required=bool(f.get("required")),
                name=f.get("name"),
                surrounding_text=f.get("surrounding_text") or "",
            )
            for f in raw
        ]

    async def fill_text(self, ref: str, value: str) -> None:
        """Human-paced typing with the full native event chain, or instant
        with real events. Re-checks for a challenge before touching the DOM."""
        assert self.page is not None
        await self.check_for_challenge(self.page.url)
        locator = self.page.locator(f"[data-jp-ref='{ref}']")
        await locator.scroll_into_view_if_needed()
        await locator.click()
        await locator.fill("")
        if self.profile.key_delay_max_ms <= 0:
            await locator.fill(value)  # instant, still dispatches input/change
        else:
            for char in value:
                await locator.type(char, delay=self.profile.key_delay_ms())
        await locator.evaluate(
            "el => { el.dispatchEvent(new Event('change', {bubbles:true}));"
            " el.dispatchEvent(new Event('blur', {bubbles:true})); }"
        )
        await asyncio.sleep(min(self.profile.field_gap_s(), 8.0))

    async def select_option(self, ref: str, option_text: str) -> None:
        assert self.page is not None
        await self.check_for_challenge(self.page.url)
        locator = self.page.locator(f"[data-jp-ref='{ref}']")
        await locator.scroll_into_view_if_needed()
        await locator.select_option(label=option_text)
        await locator.evaluate("el => el.dispatchEvent(new Event('change', {bubbles:true}))")
        await asyncio.sleep(min(self.profile.field_gap_s(), 8.0))

    async def set_checkbox(self, ref: str, checked: bool) -> None:
        assert self.page is not None
        await self.check_for_challenge(self.page.url)
        locator = self.page.locator(f"[data-jp-ref='{ref}']")
        await locator.scroll_into_view_if_needed()
        if checked:
            await locator.check()
        else:
            await locator.uncheck()

    async def choose_radio(self, name: str, value: str) -> None:
        assert self.page is not None
        await self.check_for_challenge(self.page.url)
        locator = self.page.locator(f"input[type=radio][name='{name}'][value='{value}']")
        if await locator.count() == 0:
            locator = self.page.get_by_label(value)
        await locator.first.check()

    async def upload_file(self, ref: str, path: str) -> None:
        assert self.page is not None
        await self.page.locator(f"[data-jp-ref='{ref}']").set_input_files(path)

    async def screenshot(self) -> bytes:
        assert self.page is not None
        return await self.page.screenshot(full_page=False)

    async def challenge_cleared(self) -> bool:
        """Verify the challenge element is genuinely gone before resuming."""
        assert self.page is not None
        try:
            result = await self.page.evaluate(DETECTION_JS)
            return not (result and result.get("detected"))
        except Exception:
            return True

    async def wait_until_challenge_cleared(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if await self.challenge_cleared():
                return True
            await asyncio.sleep(2.0)
        return False
