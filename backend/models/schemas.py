from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Project schemas
class ProjectBase(BaseModel):
    name: str
    address: str
    status: str
    procore_id: Optional[str] = None
    procore_synced: bool = False

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: str
    last_synced_at: Optional[datetime] = None
    total_submittals: int = 0
    pending_submittals: int = 0
    total_rfis: int = 0
    open_rfis: int = 0
    total_inspections: int = 0
    passed_inspections: int = 0
    
    class Config:
        from_attributes = True

# Submittal schemas
class SubmittalBase(BaseModel):
    project_id: str
    number: str
    title: str
    description: str
    status: str
    spec_section: str
    submitted_by: str
    submitted_date: datetime
    due_date: datetime

class SubmittalCreate(SubmittalBase):
    objects_covered: List[str] = []
    attachment_count: int = 0
    revision_number: int = 0

class Submittal(SubmittalBase):
    id: str
    ai_score: Optional[int] = None
    ai_analysis: Optional[str] = None
    objects_covered: List[str] = []
    attachment_count: int = 0
    revision_number: int = 0
    
    class Config:
        from_attributes = True

# RFI schemas
class RFIBase(BaseModel):
    project_id: str
    number: str
    subject: str
    question: str
    status: str
    priority: str
    created_by: str
    assigned_to: str
    created_date: datetime
    due_date: datetime

class RFICreate(RFIBase):
    drawing_references: List[str] = []

class RFI(RFIBase):
    id: str
    answered_date: Optional[datetime] = None
    answer: Optional[str] = None
    drawing_references: List[str] = []
    ai_suggested_response: Optional[str] = None
    
    class Config:
        from_attributes = True

# Inspection schemas
class InspectionChecklistItem(BaseModel):
    id: str
    item: str
    passed: Optional[bool] = None
    notes: Optional[str] = None

class InspectionBase(BaseModel):
    project_id: str
    number: str
    title: str
    type: str
    status: str
    scheduled_date: datetime
    inspector: str
    location: str

class InspectionCreate(InspectionBase):
    checklist: List[InspectionChecklistItem] = []
    photos: List[str] = []
    ai_findings: List[str] = []

class Inspection(InspectionBase):
    id: str
    completed_date: Optional[datetime] = None
    checklist: List[InspectionChecklistItem] = []
    photos: List[str] = []
    notes: Optional[str] = None
    ai_findings: List[str] = []
    
    class Config:
        from_attributes = True

# Drawing Object schemas
class DrawingObjectBase(BaseModel):
    project_id: str
    drawing_id: str
    object_type: str
    object_id: str
    status: str
    x: int
    y: int
    width: int
    height: int

class DrawingObjectCreate(DrawingObjectBase):
    linked_submittal_id: Optional[str] = None
    linked_inspection_id: Optional[str] = None
    metadata: dict = {}

class DrawingObject(DrawingObjectBase):
    id: str
    linked_submittal_id: Optional[str] = None
    linked_inspection_id: Optional[str] = None
    metadata: dict = {}
    
    class Config:
        from_attributes = True

# AI Insight schemas
class AIInsightBase(BaseModel):
    project_id: str
    type: str
    severity: str
    title: str
    description: str
    affected_items: List[str] = []

class AIInsightCreate(AIInsightBase):
    related_submittal_id: Optional[str] = None
    related_rfi_id: Optional[str] = None
    related_inspection_id: Optional[str] = None

class AIInsight(AIInsightBase):
    id: str
    created_at: datetime
    resolved: bool = False
    related_submittal_id: Optional[str] = None
    related_rfi_id: Optional[str] = None
    related_inspection_id: Optional[str] = None
    
    class Config:
        from_attributes = True

# Dashboard Stats
class DashboardStats(BaseModel):
    total_projects: int
    active_projects: int
    total_submittals: int
    pending_review: int
    approved_today: int
    open_rfis: int
    overdue_rfis: int
    scheduled_inspections: int
    pass_rate: int
    ai_insights_count: int
    critical_alerts: int

# Procore Connection
class ProcoreConnection(BaseModel):
    connected: bool
    last_synced_at: Optional[datetime] = None
    sync_status: str  # idle, syncing, error
    projects_linked: int
    error_message: Optional[str] = None

