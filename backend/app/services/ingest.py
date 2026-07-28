"""Listing ingestion: canonicalization, dedupe, persistence, enrichment."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import tasks as llm_tasks
from app.logging_conf import get_logger
from app.models import JobListing, User, utcnow
from app.services.normalize import similarity
from app.services.resolver import build_llm_context, load_user_data
from app.sources.base import RawListing

log = get_logger(__name__)

# Tracking parameters stripped during canonicalization.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid_src", "lever-source", "source", "src", "ref", "refid",
    "fbclid", "gclid", "mc_cid", "mc_eid", "trk", "trackingid",
}
# Parameters that identify the posting itself and must be kept.
KEEP_PARAMS = {"gh_jid", "job", "jobid", "job_id", "id", "posting", "p"}


def canonicalize_url(url: str) -> str:
    """Stable identity for a posting URL: lowercase host, no fragment, no
    tracking params. Unknown params are dropped too — canonical URLs favor
    collapse over uniqueness; KEEP_PARAMS covers the real posting ids."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    # Posting URLs on the hosts we handle are case-insensitive; lowercasing
    # the path collapses org-slug case variants of the same posting.
    path = parsed.path.rstrip("/").lower() or "/"
    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() in KEEP_PARAMS
    ]
    query = urlencode(sorted(kept))
    return urlunparse((scheme, netloc, path, "", query, ""))


_norm_re = re.compile(r"[^a-z0-9 ]+")


def _norm_title_company(title: str, company: str) -> str:
    return _norm_re.sub("", f"{title} {company}".lower()).strip()


def upsert_listings(
    db: Session, user: User, raw_listings: list[RawListing]
) -> tuple[list[JobListing], int]:
    """Insert new listings, refresh known ones. Returns (new rows, dupes)."""
    existing_by_url: dict[str, JobListing] = {
        row.canonical_url: row
        for row in db.scalars(select(JobListing).where(JobListing.user_id == user.id))
    }
    existing_fuzzy = [
        (row, _norm_title_company(row.title, row.company)) for row in existing_by_url.values()
    ]
    new_rows: list[JobListing] = []
    dupes = 0
    for raw in raw_listings:
        canonical = canonicalize_url(raw.url)
        row = existing_by_url.get(canonical)
        if row is not None:
            row.fetched_at = utcnow()
            if raw.description and not row.description:
                row.description = raw.description
            if raw.salary_min and not row.salary_min:
                row.salary_min, row.salary_max = raw.salary_min, raw.salary_max
                row.salary_currency, row.salary_period = raw.salary_currency, raw.salary_period
            dupes += 1
            continue
        # Fuzzy dedupe: same company + near-identical title from another URL.
        fuzzy_key = _norm_title_company(raw.title, raw.company)
        if any(similarity(fuzzy_key, key) >= 0.92 for _, key in existing_fuzzy):
            dupes += 1
            continue
        row = JobListing(
            user_id=user.id,
            source=raw.source,
            external_id=raw.external_id,
            canonical_url=canonical,
            apply_url=raw.apply_url or raw.url,
            title=raw.title[:300],
            company=raw.company[:300],
            location=raw.location,
            remote=raw.remote,
            salary_min=raw.salary_min,
            salary_max=raw.salary_max,
            salary_currency=raw.salary_currency,
            salary_period=raw.salary_period,
            salary_raw=raw.salary_raw,
            education_level=raw.education_level,
            posted_at=raw.posted_at,
            description=raw.description,
            fetched_at=utcnow(),
            extra=raw.extra,
        )
        db.add(row)
        existing_by_url[canonical] = row
        existing_fuzzy.append((row, fuzzy_key))
        new_rows.append(row)
    db.flush()
    return new_rows, dupes


def enrich_listings(db: Session, user: User, listings: list[JobListing], limit: int = 30) -> int:
    """One LLM pass per listing: summary, requirements, education, match."""
    data = load_user_data(db, user)
    profile_context = build_llm_context(data)
    enriched = 0
    for listing in listings[:limit]:
        if listing.summary and listing.match_score is not None:
            continue
        text = (
            f"{listing.title} at {listing.company}\n"
            f"Location: {listing.location or 'n/a'}\n\n{listing.description or ''}"
        )
        try:
            result = llm_tasks.enrich_listing(text, profile_context)
        except Exception as exc:
            log.warning("ingest.enrich_failed", listing_id=listing.id, error=str(exc))
            continue
        listing.summary = result.summary
        listing.requirements = result.requirements
        listing.match_score = result.match_score
        listing.match_rationale = result.match_rationale
        if result.education_level and not listing.education_level:
            listing.education_level = result.education_level
        enriched += 1
    db.flush()
    return enriched
