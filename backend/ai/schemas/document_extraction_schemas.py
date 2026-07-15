"""Pydantic schemas for flexible document classification, universal field extraction,
type-specific extraction, and clue generation.

Scope:
- inspection_report
- field_photo
- master_drawing
- unknown

Do not add speculative document types until real example files are available.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    INSPECTION_REPORT = "inspection_report"
    FIELD_PHOTO = "field_photo"
    MASTER_DRAWING = "master_drawing"
    UNKNOWN = "unknown"


class DocumentClassification(BaseModel):
    document_type: DocumentType
    confidence: float  # BACKEND ONLY. Never return to frontend.


class UniversalFields(BaseModel):
    project_name: Optional[str] = None
    project_number: Optional[str] = None
    location_text: Optional[str] = None
    date: Optional[str] = None
    trade: Optional[str] = None
    contractor: Optional[str] = None
    document_title: Optional[str] = None


class InspectionReportFields(BaseModel):
    inspection_name: Optional[str] = None
    inspection_status: Optional[str] = None
    items_inspected: List[str] = Field(default_factory=list)
    pass_fail_result: Optional[str] = None
    assignees: List[str] = Field(default_factory=list)
    inspection_notes: List[str] = Field(default_factory=list)


class FieldPhotoFields(BaseModel):
    visible_objects: List[str] = Field(default_factory=list)
    visible_text: List[str] = Field(default_factory=list)
    environment: Optional[str] = None
    utility_type: Optional[str] = None
    possible_location_clues: List[str] = Field(default_factory=list)
    camera_perspective: Optional[str] = None


class MasterDrawingFields(BaseModel):
    sheet_number: Optional[str] = None
    sheet_title: Optional[str] = None
    discipline: Optional[str] = None
    drawing_labels: List[str] = Field(default_factory=list)
    utility_symbols: List[str] = Field(default_factory=list)
    areas_or_zones: List[str] = Field(default_factory=list)


TYPE_SPECIFIC_SCHEMAS = {
    DocumentType.INSPECTION_REPORT: InspectionReportFields,
    DocumentType.FIELD_PHOTO: FieldPhotoFields,
    DocumentType.MASTER_DRAWING: MasterDrawingFields,
}


class Clue(BaseModel):
    type: str
    value: str
    source: str
    confidence: float  # BACKEND ONLY. Used for ranking only.
    location_relevant: bool = True
