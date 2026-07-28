from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Education, Profile, Recommendation, User, WorkExperience
from app.schemas.auth import OkResponse
from app.schemas.profile import (
    EducationIn,
    EducationOut,
    ProfileFull,
    ProfileOut,
    ProfileUpdate,
    RecommendationIn,
    RecommendationOut,
    ReorderRequest,
    WorkExperienceIn,
    WorkExperienceOut,
)

router = APIRouter()


def _get_profile(db: Session, user: User) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:  # pragma: no cover - register always creates one
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


COMPLETENESS_CHECKS: list[tuple[str, str]] = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("city", "City"),
    ("country", "Country"),
    ("authorized_countries", "Work authorization countries"),
    ("requires_sponsorship", "Sponsorship requirement"),
    ("salary_expectation_amount", "Salary expectation"),
    ("total_years_experience", "Total years of experience"),
    ("how_heard_default", "'How did you hear' default"),
    ("over_18", "Age 18+ confirmation"),
]


def _completeness(profile: Profile, has_resume: bool, has_experience: bool) -> tuple[int, list[str]]:
    missing: list[str] = []
    for attr, label in COMPLETENESS_CHECKS:
        value = getattr(profile, attr)
        if value is None or value == "" or value == []:
            missing.append(label)
    if not has_resume:
        missing.append("Default resume")
    if not has_experience:
        missing.append("Work experience")
    total = len(COMPLETENESS_CHECKS) + 2
    return round(100 * (total - len(missing)) / total), missing


@router.get("", response_model=ProfileFull)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProfileFull:
    from app.models import StoredFile

    profile = _get_profile(db, user)
    work = list(
        db.scalars(
            select(WorkExperience)
            .where(WorkExperience.user_id == user.id)
            .order_by(WorkExperience.order_index, WorkExperience.id)
        )
    )
    edu = list(
        db.scalars(
            select(Education)
            .where(Education.user_id == user.id)
            .order_by(Education.order_index, Education.id)
        )
    )
    recs = list(
        db.scalars(select(Recommendation).where(Recommendation.user_id == user.id))
    )
    has_resume = (
        db.scalar(
            select(StoredFile).where(
                StoredFile.user_id == user.id,
                StoredFile.kind == "resume",
                StoredFile.is_default_resume.is_(True),
            )
        )
        is not None
    )
    score, missing = _completeness(profile, has_resume, bool(work))
    return ProfileFull(
        profile=ProfileOut.model_validate(profile),
        work_experiences=[WorkExperienceOut.model_validate(w) for w in work],
        educations=[EducationOut.model_validate(e) for e in edu],
        recommendations=[RecommendationOut.model_validate(r) for r in recs],
        completeness=score,
        completeness_missing=missing,
    )


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Profile:
    profile = _get_profile(db, user)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "skills_years" and value is not None:
            value = {k: v if isinstance(v, dict) else v for k, v in value.items()}
        if key in ("languages", "licenses_certifications") and value is not None:
            value = [v if isinstance(v, dict) else v for v in value]
        setattr(profile, key, value)
    return profile


# --- Work experience --------------------------------------------------------


@router.post("/work-experiences", response_model=WorkExperienceOut, status_code=201)
def add_work(
    payload: WorkExperienceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WorkExperience:
    max_order = (
        db.scalar(
            select(WorkExperience.order_index)
            .where(WorkExperience.user_id == user.id)
            .order_by(WorkExperience.order_index.desc())
        )
        or 0
    )
    row = WorkExperience(user_id=user.id, order_index=max_order + 1, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


@router.put("/work-experiences/{item_id}", response_model=WorkExperienceOut)
def update_work(
    item_id: int,
    payload: WorkExperienceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkExperience:
    row = db.get(WorkExperience, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    return row


@router.delete("/work-experiences/{item_id}", response_model=OkResponse)
def delete_work(
    item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(WorkExperience, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()


@router.post("/work-experiences/reorder", response_model=OkResponse)
def reorder_work(
    payload: ReorderRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    rows = {
        r.id: r
        for r in db.scalars(select(WorkExperience).where(WorkExperience.user_id == user.id))
    }
    for index, item_id in enumerate(payload.ids):
        if item_id in rows:
            rows[item_id].order_index = index
    return OkResponse()


# --- Education --------------------------------------------------------------


@router.post("/educations", response_model=EducationOut, status_code=201)
def add_education(
    payload: EducationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Education:
    max_order = (
        db.scalar(
            select(Education.order_index)
            .where(Education.user_id == user.id)
            .order_by(Education.order_index.desc())
        )
        or 0
    )
    row = Education(user_id=user.id, order_index=max_order + 1, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


@router.put("/educations/{item_id}", response_model=EducationOut)
def update_education(
    item_id: int,
    payload: EducationIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Education:
    row = db.get(Education, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    return row


@router.delete("/educations/{item_id}", response_model=OkResponse)
def delete_education(
    item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(Education, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()


# --- Recommendations --------------------------------------------------------


@router.post("/recommendations", response_model=RecommendationOut, status_code=201)
def add_recommendation(
    payload: RecommendationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Recommendation:
    row = Recommendation(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


@router.put("/recommendations/{item_id}", response_model=RecommendationOut)
def update_recommendation(
    item_id: int,
    payload: RecommendationIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Recommendation:
    row = db.get(Recommendation, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    return row


@router.delete("/recommendations/{item_id}", response_model=OkResponse)
def delete_recommendation(
    item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(Recommendation, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()
