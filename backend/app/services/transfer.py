"""Export and import of the user's data. Round-trip must be lossless."""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.models import (
    Application,
    CustomField,
    Education,
    JobListing,
    Profile,
    Recommendation,
    SavedAnswer,
    SearchTarget,
    User,
    WorkExperience,
)

PROFILE_FIELDS = [
    "first_name", "last_name", "email", "phone", "address_line", "city", "state",
    "postal_code", "country", "linkedin_url", "portfolio_url", "github_url",
    "website_url", "pronouns", "authorized_countries", "requires_sponsorship",
    "work_model_preference", "willing_to_relocate", "salary_expectation_amount",
    "salary_expectation_currency", "salary_expectation_period",
    "current_compensation_amount", "current_compensation_currency",
    "current_compensation_period", "notice_period_days", "total_years_experience",
    "skills_years", "how_heard_default", "over_18", "consent_background_check",
    "consent_drug_screening", "security_clearance", "languages",
    "shift_availability", "licenses_certifications", "veteran_status",
    "disability_status", "gender", "race_ethnicity",
]


def _iso(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _date(value: Any) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(value) if isinstance(value, str) else value


def export_profile(db: Session, user: User) -> dict[str, Any]:
    """The complete work profile: personal block, work/education,
    recommendations, custom fields, saved answers."""
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None
    return {
        "jobpilot_export_version": 1,
        "app_version": __version__,
        "exported_at": None,  # stamped by the caller (Date.now() unavailable in some contexts)
        "profile": {field: _iso(getattr(profile, field)) for field in PROFILE_FIELDS},
        "work_experiences": [
            {
                "title": w.title, "company": w.company, "location": w.location,
                "start_date": _iso(w.start_date), "end_date": _iso(w.end_date),
                "is_current": w.is_current, "bullets": w.bullets, "order_index": w.order_index,
            }
            for w in db.scalars(
                select(WorkExperience)
                .where(WorkExperience.user_id == user.id)
                .order_by(WorkExperience.order_index)
            )
        ],
        "educations": [
            {
                "degree": e.degree, "field_of_study": e.field_of_study, "school": e.school,
                "start_date": _iso(e.start_date), "end_date": _iso(e.end_date),
                "gpa": e.gpa, "order_index": e.order_index,
            }
            for e in db.scalars(
                select(Education).where(Education.user_id == user.id).order_by(Education.order_index)
            )
        ],
        "recommendations": [
            {
                "name": r.name, "title": r.title, "relationship_to_user": r.relationship_to_user,
                "contact": r.contact, "text": r.text,
            }
            for r in db.scalars(select(Recommendation).where(Recommendation.user_id == user.id))
        ],
        "custom_fields": [
            {
                "label": c.label, "key": c.key, "type": c.type,
                "options": c.options, "value": c.value,
            }
            for c in db.scalars(select(CustomField).where(CustomField.user_id == user.id))
        ],
        "saved_answers": [
            {
                "question_key": s.question_key, "question_text": s.question_text,
                "answer": s.answer, "answer_type": s.answer_type, "source": s.source,
                "approved": s.approved, "job_family": s.job_family,
                "times_used": s.times_used, "asked_history": s.asked_history,
            }
            for s in db.scalars(select(SavedAnswer).where(SavedAnswer.user_id == user.id))
        ],
        "search_targets": [
            {
                "name": t.name, "title_terms": t.title_terms, "location": t.location,
                "remote": t.remote, "salary_floor": t.salary_floor,
                "education_level": t.education_level, "posted_within_days": t.posted_within_days,
                "exclusions": t.exclusions, "sources": t.sources,
                "schedule_minutes": t.schedule_minutes, "notify_new": t.notify_new,
            }
            for t in db.scalars(select(SearchTarget).where(SearchTarget.user_id == user.id))
        ],
    }


def import_profile(
    db: Session, user: User, data: dict[str, Any], *, merge: bool = True
) -> dict[str, int]:
    """Apply an exported profile. merge=True fills blanks and adds items;
    merge=False replaces work history / education / custom fields / saved
    answers / targets wholesale (personal block is always merged blank-fill
    or overwrite depending on merge)."""
    counts = {"profile_fields": 0, "work": 0, "education": 0, "recommendations": 0,
              "custom_fields": 0, "saved_answers": 0, "search_targets": 0}
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None
    incoming = data.get("profile", {})
    date_fields = {"earliest_start_date"}
    for field in PROFILE_FIELDS:
        if field not in incoming:
            continue
        value = incoming[field]
        if field in date_fields:
            value = _date(value)
        current = getattr(profile, field)
        if merge and current not in (None, "", [], {}):
            continue
        setattr(profile, field, value)
        counts["profile_fields"] += 1

    def _replace_or_add(model, existing_query, rows_key, builder, count_key):
        rows = data.get(rows_key, [])
        if not merge:
            for old in db.scalars(existing_query):
                db.delete(old)
            db.flush()
        for row in rows:
            db.add(builder(row))
            counts[count_key] += 1

    _replace_or_add(
        WorkExperience,
        select(WorkExperience).where(WorkExperience.user_id == user.id),
        "work_experiences",
        lambda r: WorkExperience(
            user_id=user.id, title=r["title"], company=r["company"], location=r.get("location"),
            start_date=_date(r.get("start_date")), end_date=_date(r.get("end_date")),
            is_current=r.get("is_current", False), bullets=r.get("bullets", []),
            order_index=r.get("order_index", 0),
        ),
        "work",
    )
    _replace_or_add(
        Education,
        select(Education).where(Education.user_id == user.id),
        "educations",
        lambda r: Education(
            user_id=user.id, degree=r.get("degree"), field_of_study=r.get("field_of_study"),
            school=r["school"], start_date=_date(r.get("start_date")),
            end_date=_date(r.get("end_date")), gpa=r.get("gpa"), order_index=r.get("order_index", 0),
        ),
        "education",
    )
    _replace_or_add(
        Recommendation,
        select(Recommendation).where(Recommendation.user_id == user.id),
        "recommendations",
        lambda r: Recommendation(
            user_id=user.id, name=r["name"], title=r.get("title"),
            relationship_to_user=r.get("relationship_to_user"), contact=r.get("contact"),
            text=r.get("text"),
        ),
        "recommendations",
    )

    # Custom fields and saved answers are keyed; merge upserts by key.
    _import_keyed(
        db, user, data.get("custom_fields", []), CustomField, "key", merge,
        lambda r: CustomField(
            user_id=user.id, label=r["label"], key=r["key"], type=r["type"],
            options=r.get("options", []), value=r.get("value"),
        ),
        counts, "custom_fields",
    )
    _import_keyed(
        db, user, data.get("saved_answers", []), SavedAnswer, "question_key", merge,
        lambda r: SavedAnswer(
            user_id=user.id, question_key=r["question_key"], question_text=r["question_text"],
            answer=r["answer"], answer_type=r.get("answer_type", "text"),
            source=r.get("source", "imported"), approved=r.get("approved", True),
            job_family=r.get("job_family"), times_used=r.get("times_used", 0),
            asked_history=r.get("asked_history", []),
        ),
        counts, "saved_answers",
    )
    _replace_or_add(
        SearchTarget,
        select(SearchTarget).where(SearchTarget.user_id == user.id),
        "search_targets",
        lambda r: SearchTarget(
            user_id=user.id, name=r["name"], title_terms=r.get("title_terms", []),
            location=r.get("location"), remote=r.get("remote"), salary_floor=r.get("salary_floor"),
            education_level=r.get("education_level"), posted_within_days=r.get("posted_within_days"),
            exclusions=r.get("exclusions", []), sources=r.get("sources", []),
            schedule_minutes=r.get("schedule_minutes"), notify_new=r.get("notify_new", True),
        ),
        "search_targets",
    )
    db.flush()
    return counts


def _import_keyed(db, user, rows, model, key_field, merge, builder, counts, count_key):
    existing = {
        getattr(row, key_field): row
        for row in db.scalars(select(model).where(model.user_id == user.id))
    }
    for row in rows:
        key = row[key_field]
        current = existing.get(key)
        if current is not None:
            if merge:
                continue  # keep the user's own value
            db.delete(current)
            db.flush()
        db.add(builder(row))
        counts[count_key] += 1


# --- CSV / JSON exports of job lists and application history ----------------


def listings_to_rows(listings: list[JobListing]) -> list[dict[str, Any]]:
    return [
        {
            "id": li.id, "source": li.source, "title": li.title, "company": li.company,
            "location": li.location, "remote": li.remote, "salary_min": li.salary_min,
            "salary_max": li.salary_max, "salary_currency": li.salary_currency,
            "salary_period": li.salary_period, "education_level": li.education_level,
            "match_score": li.match_score, "posted_at": _iso(li.posted_at),
            "url": li.canonical_url, "apply_url": li.apply_url, "summary": li.summary,
        }
        for li in listings
    ]


def rows_to_csv(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()


def applications_to_rows(
    db: Session, apps: list[Application], listings: dict[int, JobListing]
) -> list[dict[str, Any]]:
    rows = []
    for a in apps:
        li = listings.get(a.listing_id)
        rows.append(
            {
                "id": a.id,
                "title": li.title if li else None,
                "company": li.company if li else None,
                "source": li.source if li else None,
                "status": a.status,
                "mode": a.mode,
                "executor": a.executor,
                "submitted_at": _iso(a.submitted_at),
                "outcome": a.outcome,
                "url": li.canonical_url if li else None,
                "created_at": _iso(a.created_at),
            }
        )
    return rows


def parse_listings_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]
