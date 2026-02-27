"""
Pydantic schemas.

This file has been intentionally cleared. The project is keeping the FastAPI + SQLAlchemy
scaffolding, but removing the current table-specific schemas so new schemas can be defined
against the redesigned data model.
"""
# models/schemas.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List, Literal
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
