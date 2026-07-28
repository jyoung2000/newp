from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import CUSTOM_FIELD_TYPES, CustomField, User
from app.schemas.auth import OkResponse
from app.services.normalize import normalize_question

router = APIRouter()


class CustomFieldIn(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    type: str
    options: list[str] = Field(default_factory=list)
    value: Any | None = None
    file_id: int | None = None

    @field_validator("type")
    @classmethod
    def _type_valid(cls, v: str) -> str:
        if v not in CUSTOM_FIELD_TYPES:
            raise ValueError(f"type must be one of {CUSTOM_FIELD_TYPES}")
        return v


class CustomFieldOut(CustomFieldIn):
    id: int
    key: str
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


def _validate_value(payload: CustomFieldIn) -> None:
    v = payload.value
    if v is None:
        return
    if payload.type == "number" and not isinstance(v, (int, float)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "value must be a number")
    if payload.type == "boolean" and not isinstance(v, bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "value must be true/false")
    if payload.type == "select":
        if not payload.options:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "select needs options")
        if v not in payload.options:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "value must be one of options")
    if payload.type == "date":
        try:
            dt.date.fromisoformat(str(v))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "value must be an ISO date"
            ) from exc


@router.get("", response_model=list[CustomFieldOut])
def list_custom_fields(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CustomField]:
    return list(
        db.scalars(
            select(CustomField).where(CustomField.user_id == user.id).order_by(CustomField.id)
        )
    )


@router.post("", response_model=CustomFieldOut, status_code=201)
def create_custom_field(
    payload: CustomFieldIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CustomField:
    _validate_value(payload)
    key = normalize_question(payload.label)
    existing = db.scalar(
        select(CustomField).where(CustomField.user_id == user.id, CustomField.key == key)
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A field with this label already exists")
    row = CustomField(user_id=user.id, key=key, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


@router.put("/{field_id}", response_model=CustomFieldOut)
def update_custom_field(
    field_id: int,
    payload: CustomFieldIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomField:
    row = db.get(CustomField, field_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    _validate_value(payload)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.key = normalize_question(payload.label)
    return row


@router.delete("/{field_id}", response_model=OkResponse)
def delete_custom_field(
    field_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OkResponse:
    row = db.get(CustomField, field_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    return OkResponse()
