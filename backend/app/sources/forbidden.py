"""Boards JobPilot deliberately does not fetch from.

LinkedIn, Indeed, Monster, Glassdoor and ZipRecruiter all prohibit automated
collection in their terms of service and actively defend against it. These
stubs exist so the refusal is explicit, permanent, and visible in the UI —
not an accidental omission, and not something to hide behind a flag later.

The honest path for these boards is the user browsing them normally;
anything they find can be stored via the manual-add flow.
"""
from __future__ import annotations

from app.sources.base import NotImplementedSource


class LinkedInSource(NotImplementedSource):
    name = "linkedin"
    label = "LinkedIn"
    permission_basis = "None — the LinkedIn User Agreement prohibits automated access/scraping."
    reason = "LinkedIn's User Agreement prohibits automated access."


class IndeedSource(NotImplementedSource):
    name = "indeed"
    label = "Indeed"
    permission_basis = "None — Indeed's ToS prohibit scraping and its publisher API is invite-only."
    reason = "Indeed's terms of service prohibit scraping."


class MonsterSource(NotImplementedSource):
    name = "monster"
    label = "Monster"
    permission_basis = "None — Monster's ToS prohibit automated collection."
    reason = "Monster's terms of use prohibit automated collection."


class GlassdoorSource(NotImplementedSource):
    name = "glassdoor"
    label = "Glassdoor"
    permission_basis = "None — Glassdoor's ToS prohibit scraping."
    reason = "Glassdoor's terms of use prohibit scraping."


class ZipRecruiterSource(NotImplementedSource):
    name = "ziprecruiter"
    label = "ZipRecruiter"
    permission_basis = "None — ZipRecruiter's ToS prohibit automated access without a partner agreement."
    reason = "ZipRecruiter's terms of use prohibit automated access."
