"""
Pydantic schemas.

This file has been intentionally cleared. The project is keeping the FastAPI + SQLAlchemy
scaffolding, but removing the current table-specific schemas so new schemas can be defined
against the redesigned data model.
"""
# models/schemas.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List, Literal, Any
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True  # Allows conversion from SQLAlchemy model

# Company Schemas
class CompanyBase(BaseModel):
    name: str
    procore_company_id: str

class CompanyCreate(CompanyBase):
    pass

class CompanyResponse(CompanyBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# ============================================
# PROJECT SCHEMAS
# ============================================

ProjectStatus = Literal["active", "completed", "on_hold"]


class ProjectBase(BaseModel):
    company_id: int
    name: str = Field(..., min_length=1)
    status: ProjectStatus = "active"
    procore_project_id: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    status: Optional[ProjectStatus] = None
    procore_project_id: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============================================
# DASHBOARD SUMMARY (PROJECT-SCOPED)
# ============================================


class ProjectSummary(BaseModel):
    id: int
    name: str
    company_id: int
    procore_project_id: Optional[str] = None


class CompanyContext(BaseModel):
    active_company_id: Optional[int] = None
    project_company_id: int
    matches_active_company: bool


DashboardSyncStatus = Literal["idle", "syncing", "error"]


class SyncHealth(BaseModel):
    connected: bool
    sync_status: DashboardSyncStatus = "idle"
    project_last_sync_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None


class CurrentDrawingSummary(BaseModel):
    id: int
    name: str
    updated_at: datetime


class DashboardSummaryResponse(BaseModel):
    project: ProjectSummary
    company_context: CompanyContext
    sync_health: SyncHealth
    current_drawing: Optional[CurrentDrawingSummary] = None

# ============================================
# INSIGHTS (FINDINGS) SCHEMAS
# Frontend contract: shared/schema.ts -> AIInsight (camelCase)
# ============================================

AIInsightType = Literal["compliance", "deviation", "recommendation", "warning"]
AIInsightSeverity = Literal["low", "medium", "high", "critical"]


class AIInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, coerce_numbers_to_str=True)

    # Store as snake_case in Python (matches ORM) but serialize as camelCase (matches frontend)
    id: str
    project_id: str = Field(serialization_alias="projectId")
    type: AIInsightType
    severity: AIInsightSeverity
    title: str
    description: str
    affected_items: List[str] = Field(default_factory=list, serialization_alias="affectedItems")
    created_at: datetime = Field(serialization_alias="createdAt")
    resolved: bool
    related_submittal_id: Optional[str] = Field(default=None, serialization_alias="relatedSubmittalId")
    related_rfi_id: Optional[str] = Field(default=None, serialization_alias="relatedRFIId")
    related_inspection_id: Optional[str] = Field(default=None, serialization_alias="relatedInspectionId")

    @field_validator("affected_items", mode="before")
    @classmethod
    def _coerce_affected_items(cls, v):
        return [] if v is None else v

# Procore Connection Schemas
class ProcoreTokenCreate(BaseModel):
    company_id: int
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    procore_user_id: Optional[str] = None

class ProcoreTokenResponse(BaseModel):
    id: int
    company_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# DRAWINGS / UPLOAD SCHEMAS
# ============================================


class DrawingResponse(BaseModel):
    id: int
    name: str
    file_url: Optional[str] = None
    content_type: Optional[str] = None
    page_count: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceRecordResponse(BaseModel):
    id: int
    type: str
    trade: Optional[str] = None
    spec_section: Optional[str] = None
    title: str
    file_url: Optional[str] = None
    content_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# DRAWING REGIONS / ALIGNMENTS (Phase 2)
# ============================================
#
# Coordinate system: Store geometry NORMALIZED (0-1). Do NOT use pixel coordinates.
# This prevents resolution mismatch across different display/export contexts.
#
# Rect: { "type": "rect", "x": 0.25, "y": 0.4, "width": 0.1, "height": 0.2 }
# Polygon: { "type": "polygon", "points": [[0.1, 0.2], [0.2, 0.25], ...] }


def _check_normalized(value: float, name: str) -> None:
    if not (0 <= value <= 1):
        raise ValueError(f"{name} must be 0-1 (normalized), got {value}")


class DrawingRegionCreate(BaseModel):
    label: str
    page: int = 1
    geometry: dict  # rect or polygon, all coords normalized 0-1

    @field_validator("geometry")
    @classmethod
    def geometry_normalized(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            raise ValueError("geometry must be an object")
        gtype = v.get("type")
        if gtype == "rect":
            for key in ("x", "y", "width", "height"):
                if key in v:
                    val = v[key]
                    if not isinstance(val, (int, float)):
                        raise ValueError(f"{key} must be a number")
                    _check_normalized(float(val), key)
        elif gtype == "polygon":
            pts = v.get("points")
            if not isinstance(pts, list):
                raise ValueError("polygon must have points array")
            for i, p in enumerate(pts):
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    raise ValueError(f"point {i} must be [x, y]")
                _check_normalized(float(p[0]), f"points[{i}][0]")
                _check_normalized(float(p[1]), f"points[{i}][1]")
        else:
            raise ValueError("geometry.type must be 'rect' or 'polygon'")
        return v


class DrawingRegionResponse(BaseModel):
    id: int
    master_drawing_id: int
    label: str
    page: int
    geometry: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DrawingAlignmentCreate(BaseModel):
    sub_drawing_id: int
    region_id: Optional[int] = None
    method: str  # manual | feature_match | vision


class AlignmentTransform(BaseModel):
    """
    Minimal transform JSON contract stored in drawing_alignments.transform.
    Homography/affine matrix mapping sub-drawing coords to master.
    """
    type: str  # e.g. "homography"
    matrix: List[float]  # 9 numbers for 3x3 homography
    confidence: float = Field(ge=0.0, le=1.0)
    page: int = 1


class AlignmentUpdate(BaseModel):
    """Body for PATCH alignment status/transform."""
    status: Optional[str] = None  # queued | processing | complete | failed
    transform: Optional[AlignmentTransform] = None
    error_message: Optional[str] = None


class DrawingAlignmentResponse(BaseModel):
    id: int
    master_drawing_id: int
    sub_drawing_id: int
    region_id: Optional[int] = None
    method: str
    transform: Optional[dict] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DrawingDiffRegion(BaseModel):
    """A single diff region; geometry normalized 0-1."""
    page: int
    type: Literal["rect", "polygon"]
    points: List[List[float]]  # polygon: [[x,y],...]; rect: [[x,y],[x+w,y],[x+w,y+h],[x,y+h]] or [x,y,w,h]
    label: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class DrawingDiffCreate(BaseModel):
    """Body for POST create drawing diff."""
    alignment_id: int
    finding_id: Optional[int] = None
    summary: str
    severity: Literal["low", "medium", "high", "critical"]
    diff_regions: List[DrawingDiffRegion]


class DrawingDiffResponse(BaseModel):
    """
    Returned by API. Includes:
    - diff metadata: id, alignment_id, summary, severity, created_at
    - diff_regions: list of DrawingDiffRegion
    - finding_id: optional link to finding
    """
    id: int
    alignment_id: int
    finding_id: Optional[int] = None
    summary: str
    severity: str
    diff_regions: List[DrawingDiffRegion]
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator("diff_regions", mode="before")
    @classmethod
    def parse_diff_regions(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [DrawingDiffRegion.model_validate(x) if isinstance(x, dict) else x for x in v]
        return v


# Job Queue Schemas
class JobCreate(BaseModel):
    user_id: int
    company_id: int
    job_type: str
    input_data: dict

class JobResponse(BaseModel):
    id: int
    user_id: int
    company_id: int
    job_type: str
    status: str
    output_url: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Usage Log Schemas
class UsageLogCreate(BaseModel):
    user_id: int
    company_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    processing_time: Optional[float] = None
    metadata: Optional[dict] = None

class UsageLogResponse(UsageLogCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# User Settings Schemas
class UserSettingsUpdate(BaseModel):
    detection_mode: Optional[str] = None
    clash_threshold: Optional[float] = None
    auto_markup: Optional[bool] = None
    email_notifications: Optional[bool] = None
    slack_webhook: Optional[str] = None
    preferences: Optional[dict] = None

class UserSettingsResponse(BaseModel):
    id: int
    user_id: int
    detection_mode: str
    clash_threshold: float
    auto_markup: bool
    email_notifications: bool
    updated_at: datetime
    
    class Config:
        from_attributes = True
