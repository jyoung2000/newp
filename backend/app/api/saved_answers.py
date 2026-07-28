from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SavedAnswer, User
from app.schemas.auth import OkResponse
from app.services.normalize import normalize_question

router = APIRouter()


class SavedAnswerIn(BaseModel):
    question_text: str = Field(min_length=1)
    answer: Any
    answer_type: str = "text"
    job_family: str | None = None
    # Allows the user to adjust the normalized key so future variants match.
    question_key: str | None = None
    approved: bool = True


class SavedAnswerOut(BaseModel):
    id: int
    question_key: str
    question_text: str
    answer: Any
    answer_type: str
    times_used: int
    last_used_at: dt.datetime | None
    source: str
    approved: bool
    job_family: str | None
    asked_history: list[dict[str, Any]]
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[SavedAnswerOut])
def list_saved_answers(
    q: str | None = Query(default=None, description="Search question text and answers"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedAnswer]:
    stmt = select(SavedAnswer).where(SavedAnswer.user_id == user.id)
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                SavedAnswer.question_text.ilike(needle),
                SavedAnswer.question_key.ilike(needle),
            )
        )
    return list(db.scalars(stmt.order_by(SavedAnswer.times_used.desc(), SavedAnswer.id.desc())))


@router.post("", response_model=SavedAnswerOut, status_code=201)
def create_saved_answer(
    payload: SavedAnswerIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SavedAnswer:
    key = payload.question_key or normalize_question(payload.question_text)
    existing = db.scalar(
        select(SavedAnswer).where(SavedAnswer.user_id == user.id, SavedAnswer.question_key == key)
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An answer for this question already exists")
    row = SavedAnswer(
        user_id=user.id,
        question_key=key,
        question_text=payload.question_text,
        answer=payload.answer,
        answer_type=payload.answer_type,
        job_family=payload.job_family,
        approved=payload.approved,
        source="user",
    )
    db.add(row)
    db.flush()
    return row


@router.put("/{answer_id}", response_model=SavedAnswerOut)
def update_saved_answer(
    answer_id: int,
    payload: SavedAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedAnswer:
    row = db.get(SavedAnswer, answer_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.question_text = payload.question_text
    row.question_key = payload.question_key or normalize_question(payload.question_text)
    row.answer = payload.answer
    row.answer_type = payload.answer_type
    row.job_family = payload.job_family
    row.approved = payload.approved
    return row


@router.post("/{answer_id}/approve", response_model=SavedAnswerOut)
def approve_saved_answer(
    answer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SavedAnswer:
    """Approve a generated draft for auto-mode reuse in its job family."""
    row = db.get(SavedAnswer, answer_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.approved = True
    return row


@router.delete("/{answer_id}", response_model=OkResponse)
def delete_saved_answer(
    answer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(SavedAnswer, answer_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()
