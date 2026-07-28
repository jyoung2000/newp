"""Humanized-input timing profiles.

Why this exists (see README "Type like a human"): modern ATS forms built on
React/Vue/Angular register state only on real event sequences, and many
multi-step wizards won't enable "Next" without a genuine blur. Human-paced
entry with the full native event chain is simply the reliable way to fill
them correctly — and it naturally paces requests instead of firing a burst.

What it is NOT: cloaking. There is no fingerprint spoofing, no
navigator.webdriver patching, no stealth plugin anywhere in this project
(the architectural test enforces that), and CAPTCHAs always go to a human
regardless of this setting.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class TimingProfile:
    # Per-character typing delay, milliseconds.
    key_delay_min_ms: int = 60
    key_delay_max_ms: int = 180
    # Occasional longer pause probability/duration while typing.
    pause_chance: float = 0.06
    pause_min_ms: int = 350
    pause_max_ms: int = 1200
    # "Reading time" between fields, seconds.
    field_gap_min_s: float = 2.0
    field_gap_max_s: float = 8.0
    # Think time between pages of a wizard, seconds.
    page_gap_min_s: float = 2.0
    page_gap_max_s: float = 6.0
    # Randomized think-time between jobs, seconds.
    between_jobs_min_s: float = 20.0
    between_jobs_max_s: float = 90.0
    # Pointer movement steps before a click.
    mouse_steps: int = 12

    def key_delay_ms(self) -> float:
        if random.random() < self.pause_chance:
            return random.uniform(self.pause_min_ms, self.pause_max_ms)
        return random.uniform(self.key_delay_min_ms, self.key_delay_max_ms)

    def field_gap_s(self) -> float:
        return random.uniform(self.field_gap_min_s, self.field_gap_max_s)

    def page_gap_s(self) -> float:
        return random.uniform(self.page_gap_min_s, self.page_gap_max_s)

    def between_jobs_s(self) -> float:
        return random.uniform(self.between_jobs_min_s, self.between_jobs_max_s)


HUMANIZED = TimingProfile()

# Instant mode: no artificial pacing, but fills still dispatch the real
# native event chain so controlled components register the input.
INSTANT = TimingProfile(
    key_delay_min_ms=0,
    key_delay_max_ms=0,
    pause_chance=0.0,
    field_gap_min_s=0.05,
    field_gap_max_s=0.15,
    page_gap_min_s=0.2,
    page_gap_max_s=0.5,
    between_jobs_min_s=1.0,
    between_jobs_max_s=3.0,
    mouse_steps=1,
)


def profile_for(humanize: bool) -> TimingProfile:
    return HUMANIZED if humanize else INSTANT
