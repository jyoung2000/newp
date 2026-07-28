"""Boards JobPilot deliberately does not fetch from.

LinkedIn, Indeed, Monster, Glassdoor and ZipRecruiter all prohibit automated
collection in their terms of service and actively defend against it. These
stubs exist so the refusal is explicit, permanent, and visible in the UI —
not an accidental omission, and not something to hide behind a flag later.

The route that does work for these boards is you: browse one normally, and on
a posting you are already reading click the extension's "Save this job"
button — the page content comes from your browser, JobPilot never requests the
URL itself. The manual-add flow stores a listing you paste in the same way, and
a company's own partner API is fine where the user holds credentials for it.
"""
from __future__ import annotations

from app.sources.base import NotImplementedSource


class LinkedInSource(NotImplementedSource):
    name = "linkedin"
    label = "LinkedIn"
    permission_basis = (
        "None — the LinkedIn User Agreement prohibits automated access/scraping. "
        "Browse LinkedIn yourself and click the extension's 'Save this job' button on a "
        "posting, or use LinkedIn's official partner API if you hold credentials for it."
    )
    reason = (
        "LinkedIn's User Agreement prohibits automated access. Open the posting in your own "
        "browser and click the extension's 'Save this job' button, or use LinkedIn's official "
        "partner API if you hold credentials for it."
    )


class IndeedSource(NotImplementedSource):
    name = "indeed"
    label = "Indeed"
    permission_basis = (
        "None — Indeed's ToS prohibit scraping and its publisher API is invite-only. "
        "Browse Indeed yourself and click the extension's 'Save this job' button on a "
        "posting, or use Indeed's publisher API if you have been granted access to it."
    )
    reason = (
        "Indeed's terms of service prohibit scraping. Open the posting in your own browser "
        "and click the extension's 'Save this job' button, or use Indeed's publisher API if "
        "you have been granted access to it."
    )


class MonsterSource(NotImplementedSource):
    name = "monster"
    label = "Monster"
    permission_basis = (
        "None — Monster's ToS prohibit automated collection. Browse Monster yourself and "
        "click the extension's 'Save this job' button on a posting, or use Monster's partner "
        "API if you hold credentials for it."
    )
    reason = (
        "Monster's terms of use prohibit automated collection. Open the posting in your own "
        "browser and click the extension's 'Save this job' button, or use Monster's partner "
        "API if you hold credentials for it."
    )


class GlassdoorSource(NotImplementedSource):
    name = "glassdoor"
    label = "Glassdoor"
    permission_basis = (
        "None — Glassdoor's ToS prohibit scraping. Browse Glassdoor yourself and click the "
        "extension's 'Save this job' button on a posting, or use Glassdoor's partner API if "
        "you hold credentials for it."
    )
    reason = (
        "Glassdoor's terms of use prohibit scraping. Open the posting in your own browser and "
        "click the extension's 'Save this job' button, or use Glassdoor's partner API if you "
        "hold credentials for it."
    )


class ZipRecruiterSource(NotImplementedSource):
    name = "ziprecruiter"
    label = "ZipRecruiter"
    permission_basis = (
        "None — ZipRecruiter's ToS prohibit automated access without a partner agreement. "
        "Browse ZipRecruiter yourself and click the extension's 'Save this job' button on a "
        "posting, or use its partner API under an agreement you hold."
    )
    reason = (
        "ZipRecruiter's terms of use prohibit automated access. Open the posting in your own "
        "browser and click the extension's 'Save this job' button, or use ZipRecruiter's "
        "partner API under an agreement you hold."
    )
