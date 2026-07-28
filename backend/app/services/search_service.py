"""Search orchestration: runs a query across the selected sources with live
progress, harvests discovered org slugs, ingests + enriches results.

Runs in a background thread when triggered from the API (progress streams
over WebSocket) and inside the arq worker for scheduled saved searches —
same code path either way.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.logging_conf import get_logger
from app.models import DiscoveredOrg, JobListing, SourceState, User, utcnow
from app.services.ingest import enrich_listings, upsert_listings
from app.sources import (
    ForbiddenSourceError,
    NotImplementedSource,
    WebSearchDiscovery,
    get_sources,
)
from app.sources.base import OrgRef, SearchQuery
from app.sources.http import SourceBlockedError, get_http
from app.sources.jsonld import fetch_jobpostings
from app.sources.websearch import harvest_org_refs
from app.ws import publish_sync

log = get_logger(__name__)

BLOCK_BACKOFF_HOURS = 6


@dataclass
class SearchRun:
    id: str
    user_id: int
    status: str = "running"  # running / completed / failed
    total_sources: int = 0
    completed_sources: int = 0
    found: int = 0
    new: int = 0
    per_source: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None
    listing_ids: list[int] = field(default_factory=list)


_RUNS: dict[str, SearchRun] = {}
_RUNS_LOCK = threading.Lock()


def get_run(run_id: str) -> SearchRun | None:
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def start_search_thread(user_id: int, query: SearchQuery, source_names: list[str]) -> str:
    run = SearchRun(id=uuid.uuid4().hex[:12], user_id=user_id)
    with _RUNS_LOCK:
        _RUNS[run.id] = run
        if len(_RUNS) > 50:
            done = [k for k, v in _RUNS.items() if v.status != "running"]
            for key in done[:-20]:
                del _RUNS[key]
    thread = threading.Thread(
        target=_run_search_safely, args=(run, query, source_names), daemon=True
    )
    thread.start()
    return run.id


def _run_search_safely(run: SearchRun, query: SearchQuery, source_names: list[str]) -> None:
    session = get_sessionmaker()()
    try:
        user = session.get(User, run.user_id)
        assert user is not None
        execute_search(session, user, query, source_names, run)
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        run.status = "failed"
        run.error = str(exc)
        log.exception("search.run_failed", run_id=run.id)
    finally:
        session.close()
        _notify(run)


def _notify(run: SearchRun) -> None:
    publish_sync(
        run.user_id,
        {
            "type": "search.progress",
            "run_id": run.id,
            "status": run.status,
            "total_sources": run.total_sources,
            "completed_sources": run.completed_sources,
            "found": run.found,
            "new": run.new,
            "per_source": run.per_source,
        },
    )


def _source_state(db: Session, user: User, name: str) -> SourceState:
    state = db.scalar(
        select(SourceState).where(SourceState.user_id == user.id, SourceState.source == name)
    )
    if state is None:
        state = SourceState(user_id=user.id, source=name, status="ok")
        db.add(state)
        db.flush()
    return state


def _load_orgs(db: Session, user: User) -> list[OrgRef]:
    rows = db.scalars(
        select(DiscoveredOrg).where(
            DiscoveredOrg.user_id == user.id, DiscoveredOrg.active.is_(True)
        )
    )
    return [OrgRef(ats=r.ats, slug=r.slug, company_name=r.company_name) for r in rows]


def _save_orgs(db: Session, user: User, refs: list[OrgRef]) -> int:
    added = 0
    for ref in refs:
        existing = db.scalar(
            select(DiscoveredOrg).where(
                DiscoveredOrg.user_id == user.id,
                DiscoveredOrg.ats == ref.ats,
                DiscoveredOrg.slug == ref.slug,
            )
        )
        if existing is not None:
            existing.last_seen_at = utcnow()
            continue
        db.add(
            DiscoveredOrg(
                user_id=user.id,
                ats=ref.ats,
                slug=ref.slug,
                company_name=ref.company_name,
                last_seen_at=utcnow(),
            )
        )
        added += 1
    db.flush()
    return added


def execute_search(
    db: Session,
    user: User,
    query: SearchQuery,
    source_names: list[str],
    run: SearchRun,
) -> None:
    http = get_http()
    all_sources = {s.name: s for s in get_sources()}
    wanted = source_names or [
        s.name for s in get_sources() if not isinstance(s, NotImplementedSource)
    ]
    sources = [all_sources[n] for n in wanted if n in all_sources]
    run.total_sources = len(sources)
    _notify(run)

    # Web-search discovery runs first so freshly harvested org slugs feed
    # the board connectors within the same run.
    discovery = next((s for s in sources if isinstance(s, WebSearchDiscovery)), None)
    if discovery is not None:
        run.per_source[discovery.name] = {"status": "running", "found": 0}
        _notify(run)
        state = _source_state(db, user, discovery.name)
        if not discovery.is_configured():
            state.status = "disabled"
            state.detail = "No Brave Search or SerpAPI key configured"
            run.per_source[discovery.name] = {"status": "disabled", "found": 0}
        else:
            results = discovery.run_queries(query, http)
            refs = harvest_org_refs([r.url for r in results])
            added = _save_orgs(db, user, refs)
            direct = 0
            for result in results[:10]:
                try:
                    postings = fetch_jobpostings(result.url, http)
                except Exception:
                    continue
                if postings:
                    new_rows, _ = upsert_listings(db, user, postings)
                    run.listing_ids.extend(r.id for r in new_rows)
                    run.new += len(new_rows)
                    direct += len(postings)
            state.status = "ok"
            state.detail = f"{len(results)} results, {added} new orgs"
            run.per_source[discovery.name] = {
                "status": "done", "found": direct, "orgs_added": added,
            }
        run.completed_sources += 1
        db.commit()
        _notify(run)

    orgs = _load_orgs(db, user)

    for source in sources:
        if isinstance(source, WebSearchDiscovery):
            continue
        run.per_source[source.name] = {"status": "running", "found": 0}
        _notify(run)
        state = _source_state(db, user, source.name)

        if isinstance(source, NotImplementedSource):
            state.status = "forbidden"
            run.per_source[source.name] = {"status": "forbidden", "found": 0}
            run.completed_sources += 1
            continue
        if not source.is_configured():
            state.status = "disabled"
            state.detail = "API key not configured"
            run.per_source[source.name] = {"status": "disabled", "found": 0}
            run.completed_sources += 1
            continue
        blocked_until = state.blocked_until
        if state.status == "blocked" and blocked_until is not None:
            if blocked_until.tzinfo is None:
                import datetime as dt

                blocked_until = blocked_until.replace(tzinfo=dt.UTC)
            if blocked_until > utcnow():
                run.per_source[source.name] = {
                    "status": "blocked", "found": 0, "until": blocked_until.isoformat(),
                }
                run.completed_sources += 1
                continue

        try:
            raw = source.search(query, http, orgs)
            new_rows, dupes = upsert_listings(db, user, raw)
            run.listing_ids.extend(r.id for r in new_rows)
            run.found += len(raw)
            run.new += len(new_rows)
            state.status = "ok"
            state.detail = None
            state.blocked_until = None
            run.per_source[source.name] = {
                "status": "done", "found": len(raw), "new": len(new_rows), "dupes": dupes,
            }
        except ForbiddenSourceError as exc:
            state.status = "forbidden"
            state.detail = str(exc)
            run.per_source[source.name] = {"status": "forbidden", "found": 0}
        except SourceBlockedError as exc:
            import datetime as dt

            state.status = "blocked"
            state.detail = exc.reason
            state.blocked_until = utcnow() + dt.timedelta(hours=BLOCK_BACKOFF_HOURS)
            run.per_source[source.name] = {"status": "blocked", "found": 0, "reason": exc.reason}
            log.warning("search.source_blocked", source=source.name, reason=exc.reason)
        except Exception as exc:
            state.detail = str(exc)
            run.per_source[source.name] = {"status": "error", "found": 0, "error": str(exc)[:200]}
            log.warning("search.source_error", source=source.name, error=str(exc))
        run.completed_sources += 1
        db.commit()
        _notify(run)

    # Enrichment pass over this run's new listings.
    if run.listing_ids:
        listings = list(
            db.scalars(select(JobListing).where(JobListing.id.in_(run.listing_ids)))
        )
        enrich_listings(db, user, listings)
        db.commit()

    run.status = "completed"
    _notify(run)
