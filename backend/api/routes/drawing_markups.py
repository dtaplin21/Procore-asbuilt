"""Routes for contract-drawing markups. Mount with ``app.include_router(drawing_markups.router)``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Drawing
from services import drawing_markups as svc

router = APIRouter(tags=["drawing-markups"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user_name(x_procore_user: str | None = Header(default=None)) -> str:
    """Replace with the app's real auth dependency. This reads the name the embed bridge sends."""
    return (x_procore_user or "unknown").strip() or "unknown"


class MarkupIn(BaseModel):
    page: int = Field(default=1, ge=1)
    kind: str
    points: list[list[float]]
    label: str | None = None
    inspection_type: str | None = None
    status: str | None = None
    color: str | None = None


class MarkupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[list[float]] | None = None
    label: str | None = None
    inspection_type: str | None = None
    status: str | None = None
    color: str | None = None


class MarkupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: int
    drawingId: int = Field(validation_alias="drawing_id")
    page: int
    kind: str
    points: list[list[float]] = Field(validation_alias="points_json")
    label: str | None
    inspectionType: str | None = Field(validation_alias="inspection_type")
    status: str | None
    color: str | None
    createdBy: str = Field(validation_alias="created_by")
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


def _drawing_or_404(db: Session, drawing_id: int) -> None:
    if db.get(Drawing, drawing_id) is None:
        raise HTTPException(404, f"drawing {drawing_id} not found")


@router.get("/api/drawings/{drawing_id}/markups", response_model=list[MarkupOut])
def list_markups(
    drawing_id: int,
    page: int | None = Query(default=None, ge=1),
    inspection_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    _drawing_or_404(db, drawing_id)
    try:
        return svc.list_markups(db, drawing_id, page=page, inspection_type=inspection_type, status=status)
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/drawings/{drawing_id}/markups", response_model=MarkupOut, status_code=201)
def create_markup(drawing_id: int, body: MarkupIn, db: Session = Depends(get_db), user: str = Depends(current_user_name)):
    _drawing_or_404(db, drawing_id)
    try:
        return svc.create_markup(
            db, drawing_id=drawing_id, page=body.page, created_by=user, kind=body.kind, points=body.points,
            label=body.label, inspection_type=body.inspection_type, status=body.status, color=body.color,
        )
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/api/markups/{markup_id}", response_model=MarkupOut)
def patch_markup(markup_id: int, body: MarkupPatch, db: Session = Depends(get_db)):
    row = svc.get_markup(db, markup_id)
    if row is None:
        raise HTTPException(404, "markup not found")
    try:
        return svc.update_markup(db, row, body.model_dump(exclude_unset=True))
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/api/markups/{markup_id}", status_code=204)
def remove_markup(markup_id: int, db: Session = Depends(get_db)):
    row = svc.get_markup(db, markup_id)
    if row is None:
        raise HTTPException(404, "markup not found")
    svc.delete_markup(db, row)


@router.get("/api/drawings/{drawing_id}/markups/summary")
def markup_summary(drawing_id: int, page: int | None = Query(default=None, ge=1), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _drawing_or_404(db, drawing_id)
    return svc.summary(db, drawing_id, page)
