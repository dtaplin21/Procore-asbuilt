from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    status = Column(String, nullable=False)  # active, completed, on_hold
    procore_id = Column(String, nullable=True)
    procore_synced = Column(Boolean, default=False)
    last_synced_at = Column(DateTime, nullable=True)
    total_submittals = Column(Integer, default=0)
    pending_submittals = Column(Integer, default=0)
    total_rfis = Column(Integer, default=0)
    open_rfis = Column(Integer, default=0)
    total_inspections = Column(Integer, default=0)
    passed_inspections = Column(Integer, default=0)

class Submittal(Base):
    __tablename__ = "submittals"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    number = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    spec_section = Column(String, nullable=False)
    submitted_by = Column(String, nullable=False)
    submitted_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    ai_score = Column(Integer, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    objects_covered = Column(JSON, default=list)
    attachment_count = Column(Integer, default=0)
    revision_number = Column(Integer, default=0)

class RFI(Base):
    __tablename__ = "rfis"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    number = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    created_by = Column(String, nullable=False)
    assigned_to = Column(String, nullable=False)
    created_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    answered_date = Column(DateTime, nullable=True)
    answer = Column(Text, nullable=True)
    drawing_references = Column(JSON, default=list)
    ai_suggested_response = Column(Text, nullable=True)

class Inspection(Base):
    __tablename__ = "inspections"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    number = Column(String, nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    completed_date = Column(DateTime, nullable=True)
    inspector = Column(String, nullable=False)
    location = Column(String, nullable=False)
    checklist = Column(JSON, default=list)
    photos = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    ai_findings = Column(JSON, default=list)

class DrawingObject(Base):
    __tablename__ = "drawing_objects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    drawing_id = Column(String, nullable=False)
    object_type = Column(String, nullable=False)
    object_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    linked_submittal_id = Column(String, nullable=True)
    linked_inspection_id = Column(String, nullable=True)
    metadata = Column(JSON, default=dict)

class AIInsight(Base):
    __tablename__ = "ai_insights"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    affected_items = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    related_submittal_id = Column(String, nullable=True)
    related_rfi_id = Column(String, nullable=True)
    related_inspection_id = Column(String, nullable=True)

