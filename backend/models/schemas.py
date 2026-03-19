"""
Pydantic schemas.

This file has been intentionally cleared. The project is keeping the FastAPI + SQLAlchemy
scaffolding, but removing the current table-specific schemas so new schemas can be defined
against the redesigned data model.
"""
# models/schemas.py
from pydantic import AliasChoices, BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List, Literal, Any, Dict
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


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""
    items: List[ProjectResponse]
    total: int
    limit: int
    offset: int


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


class ProjectSummaryKpis(BaseModel):
    total_findings: int = 0
    open_findings: int = 0
    drawings_count: int = 0
    evidence_count: int = 0
    inspections_count: int = 0


class DashboardSummaryResponse(BaseModel):
    project: ProjectSummary
    company_context: CompanyContext
    sync_health: SyncHealth
    current_drawing: Optional[CurrentDrawingSummary] = None
    kpis: ProjectSummaryKpis = Field(default_factory=ProjectSummaryKpis)

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
    drawing_id: Optional[int] = Field(default=None, serialization_alias="relatedDrawingId")

    @field_validator("affected_items", mode="before")
    @classmethod
    def _coerce_affected_items(cls, v):
        return [] if v is None else v


class InsightListResponse(BaseModel):
    """Paginated list of AI findings/insights."""
    items: List[AIInsightResponse]
    total: int
    limit: int
    offset: int


class FindingListResponse(BaseModel):
    """Project-scoped findings list (dashboard)."""
    findings: List[AIInsightResponse]


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


class DrawingCompareRequest(BaseModel):
    sub_drawing_id: int = Field(
        ...,
        serialization_alias="subDrawingId",
        validation_alias=AliasChoices("subDrawingId", "sub_drawing_id"),
    )

    model_config = {"populate_by_name": True}


class DrawingSummary(BaseModel):
    id: int
    project_id: int = Field(..., serialization_alias="projectId")
    source: Optional[str] = None
    name: str
    file_url: Optional[str] = Field(default=None, serialization_alias="fileUrl")
    content_type: Optional[str] = Field(default=None, serialization_alias="contentType")
    page_count: Optional[int] = Field(default=None, serialization_alias="pageCount")

    model_config = {"from_attributes": True, "populate_by_name": True}


class EvidenceRecordResponse(BaseModel):
    id: int
    type: str
    trade: Optional[str] = None
    spec_section: Optional[str] = None
    title: str
    status: Optional[str] = None
    source_id: Optional[str] = None
    text_content: Optional[str] = None
    dates: Optional[Dict[str, Any]] = None
    attachments_json: Optional[List[Any]] = None
    cross_refs_json: Optional[List[Any]] = None
    file_url: Optional[str] = None
    content_type: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EvidenceRecordCreate(BaseModel):
    type: str
    title: str
    status: Optional[str] = "new"
    source_id: Optional[str] = None
    text_content: Optional[str] = None
    dates: Optional[Dict[str, Any]] = None
    attachments_json: Optional[List[Any]] = None
    cross_refs_json: Optional[List[Any]] = None


class EvidenceRecordUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    source_id: Optional[str] = None
    text_content: Optional[str] = None
    dates: Optional[Dict[str, Any]] = None
    attachments_json: Optional[List[Any]] = None
    cross_refs_json: Optional[List[Any]] = None


class EvidenceRecordListResponse(BaseModel):
    evidence_records: List[EvidenceRecordResponse]


class EvidenceListResponse(BaseModel):
    """Paginated list of document evidence records."""
    items: List[EvidenceRecordResponse]
    total: int
    limit: int
    offset: int


class RfiIngestionResponse(BaseModel):
    imported_count: int
    records: List[EvidenceRecordResponse]


class EvidenceDrawingLinkResponse(BaseModel):
    id: int
    project_id: int
    evidence_id: int
    drawing_id: int
    link_type: str
    matched_text: str | None = None
    confidence: float | None = None
    source: str
    is_primary: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class EvidenceDrawingLinkCreate(BaseModel):
    drawing_id: int
    link_type: str = "manual"
    matched_text: Optional[str] = None
    confidence: Optional[float] = None
    source: str = "manual"
    is_primary: bool = False


class EvidenceDrawingLinkListResponse(BaseModel):
    links: List[EvidenceDrawingLinkResponse]


class EvidenceMatchReason(BaseModel):
    reason: str
    weight: float
    details: Optional[Dict[str, Any]] = None


class EvidenceContextMatch(BaseModel):
    evidence: EvidenceRecordResponse
    score: float
    reasons: List[EvidenceMatchReason]
    direct_links: List[EvidenceDrawingLinkResponse] = Field(default_factory=list, serialization_alias="directLinks")
    discipline_overlap: List[str] = Field(default_factory=list, serialization_alias="disciplineOverlap")
    revision_proximity_days: Optional[int] = Field(
        default=None,
        serialization_alias="revisionProximityDays",
    )


class EvidenceContextResponse(BaseModel):
    drawing: DrawingResponse
    matches: List[EvidenceContextMatch]


class InspectionListResponse(BaseModel):
    """Paginated list of inspection records (dict items)."""
    items: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


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


class DrawingTransformResponse(BaseModel):
    """
    Rich transform shape for production alignments.
    Supports affine/homography math, confidence + error metrics for QC.
    """
    type: str
    matrix: Optional[Dict[str, float]] = None
    homography: Optional[List[float]] = None
    confidence: Optional[float] = None
    residual_error: Optional[float] = None
    source_points: Optional[List[Dict[str, float]]] = None
    target_points: Optional[List[Dict[str, float]]] = None
    page: Optional[int] = None


class AlignmentUpdate(BaseModel):
    """Body for PATCH alignment status/transform."""
    status: Optional[str] = None  # queued | processing | complete | failed
    transform: Optional[AlignmentTransform] = None
    error_message: Optional[str] = None


class DrawingAlignmentResponse(BaseModel):
    id: int
    project_id: Optional[int] = Field(default=None, serialization_alias="projectId")
    master_drawing_id: int = Field(..., serialization_alias="masterDrawingId")
    sub_drawing_id: int = Field(..., serialization_alias="subDrawingId")
    transform_matrix: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="transformMatrix", validation_alias="transform")
    alignment_status: Optional[str] = Field(default=None, serialization_alias="alignmentStatus", validation_alias="status")
    created_at: Optional[str] = Field(default=None, serialization_alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_to_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v else None


class DrawingAlignmentListResponse(BaseModel):
    """Paginated list of drawing alignments."""
    items: List[DrawingAlignmentResponse]
    total: int
    limit: int
    offset: int


class DrawingDiffRegion(BaseModel):
    """A single diff region; geometry normalized 0-1."""
    page: Optional[int] = None
    bbox: Optional[Dict[str, Any]] = None
    change_type: Optional[str] = Field(default=None, serialization_alias="changeType")
    note: Optional[str] = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class DrawingDiffCreate(BaseModel):
    """Body for POST create drawing diff (manual)."""
    alignment_id: int
    finding_id: Optional[int] = None
    summary: str
    severity: Literal["low", "medium", "high", "critical"]
    diff_regions: List[DrawingDiffRegion]


class RunDrawingDiffRequest(BaseModel):
    """Body for POST run drawing diff pipeline."""
    alignment_id: int
    strategy: str = "default"


class DrawingDiffResponse(BaseModel):
    id: int
    alignment_id: int = Field(..., serialization_alias="alignmentId")
    summary: Optional[str] = None
    status: Optional[str] = Field(default=None, validation_alias="severity")
    diff_regions: List[DrawingDiffRegion] = Field(default_factory=list, serialization_alias="diffRegions")
    created_at: Optional[str] = Field(default=None, serialization_alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("diff_regions", mode="before")
    @classmethod
    def parse_diff_regions(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [DrawingDiffRegion.model_validate(x) if isinstance(x, dict) else x for x in v]
        return v

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_to_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v else None


class DrawingDiffListResponse(BaseModel):
    """Paginated list of diffs."""
    items: List[DrawingDiffResponse]
    total: int
    limit: int
    offset: int


class DrawingComparisonWorkspaceResponse(BaseModel):
    master_drawing: DrawingSummary = Field(..., serialization_alias="masterDrawing")
    sub_drawing: DrawingSummary = Field(..., serialization_alias="subDrawing")
    alignment: DrawingAlignmentResponse
    diffs: List[DrawingDiffResponse]

    model_config = {"populate_by_name": True}


# ============================================
# INSPECTION RUNS / OVERLAYS / GEOMETRY
# ============================================
#
# Geometry contract (MVP): normalized coords 0-1 in master space
# { "page": 1, "type": "polygon", "points": [{"x":0.1,"y":0.2}, ...], "label": "...", "confidence": 0.88 }
#


class OverlayPoint(BaseModel):
    """Normalized point in master drawing space (0-1)."""
    x: float = Field(ge=0.0, le=1.0, description="Normalized x (0-1)")
    y: float = Field(ge=0.0, le=1.0, description="Normalized y (0-1)")


OverlayGeometryType = Literal["polygon", "rect"]


class OverlayGeometry(BaseModel):
    """Validated geometry for overlays; normalized 0-1 in master drawing space."""
    page: int = Field(ge=1, description="Page number (1-based)")
    type: OverlayGeometryType
    points: List[OverlayPoint]
    label: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    @field_validator("points")
    @classmethod
    def points_non_empty(cls, v: List[OverlayPoint]) -> List[OverlayPoint]:
        if not v:
            raise ValueError("points must not be empty")
        return v


# ----- Request bodies -----


class InspectionRunCreate(BaseModel):
    """Body for POST create inspection run."""
    master_drawing_id: int
    evidence_id: Optional[int] = None
    inspection_type: Optional[str] = None  # allow override


class ProcoreWritebackRequest(BaseModel):
    """Body for POST Procore writeback."""
    inspection_run_id: int
    mode: Literal["dry_run", "commit"]


class InspectionItemWritebackRequest(BaseModel):
    """Body for POST Procore inspection items writeback (items only; inspection header must exist)."""
    inspection_run_id: int
    mode: Literal["dry_run", "commit"]


class InspectionItemWritebackResponse(BaseModel):
    """Response for inspection items writeback. mode indicates what was done."""
    mode: str  # "dry_run" | "commit"
    inspection_items_contract: Optional[list] = None  # dry_run: derived item contract
    inspection_item_payloads: Optional[list] = None  # dry_run: translated item payloads
    procore_inspection_items: Optional[list] = None  # commit: created items from Procore


class ObservationWritebackRequest(BaseModel):
    """Body for POST Procore observation writeback (Finding → Procore Observation)."""
    finding_id: int
    mode: Literal["dry_run", "commit"]


class PunchItemWritebackRequest(BaseModel):
    """Body for POST Procore punch item writeback (Finding → Procore Punch Item)."""
    finding_id: int
    mode: Literal["dry_run", "commit"]


class PunchItemWritebackResponse(BaseModel):
    """Response for punch item writeback. mode indicates what was done."""
    mode: str  # "dry_run" | "commit"
    contract: Optional[dict] = None  # dry_run: normalized contract
    payload: Optional[dict] = None  # dry_run: Procore payload that would be sent
    procore_punch_item: Optional[dict] = None  # commit: created punch item from Procore


class ObservationWritebackResponse(BaseModel):
    """Response for observation writeback. mode indicates what was done."""
    mode: str  # "dry_run" | "commit"
    contract: Optional[dict] = None  # dry_run: normalized contract
    payload: Optional[dict] = None  # dry_run: Procore payload that would be sent
    procore_observation: Optional[dict] = None  # commit: created observation from Procore


class ProcoreWritebackResponse(BaseModel):
    """Response for Procore writeback. mode indicates what was done."""
    mode: str  # "dry_run" | "commit"
    payload: Optional[dict] = None
    committed: Optional[bool] = None  # commit: True if write succeeded, False otherwise
    procore_response: Optional[dict] = None  # commit: Procore API response (nullable)
    message: Optional[str] = None


# ----- Response models -----


class InspectionRunResponse(BaseModel):
    id: int
    project_id: int
    master_drawing_id: int
    evidence_id: Optional[int] = None
    inspection_type: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InspectionResultResponse(BaseModel):
    id: int
    inspection_run_id: int
    outcome: str
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DrawingOverlayResponse(BaseModel):
    id: int
    master_drawing_id: int
    inspection_run_id: Optional[int] = None
    diff_id: Optional[int] = None
    geometry: dict  # OverlayGeometry structure (validated on create)
    status: str
    meta: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InspectionRunListResponse(BaseModel):
    """Paginated list of inspection runs."""
    items: List[InspectionRunResponse]
    total: int
    limit: int
    offset: int


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


class JobListResponse(BaseModel):
    jobs: List[JobResponse]

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
