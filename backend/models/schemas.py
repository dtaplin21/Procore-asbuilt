"""
Pydantic schemas.

This file has been intentionally cleared. The project is keeping the FastAPI + SQLAlchemy
scaffolding, but removing the current table-specific schemas so new schemas can be defined
against the redesigned data model.
"""
# models/schemas.py
from pydantic import BaseModel, EmailStr, Field
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
