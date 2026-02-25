# models/database.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, JSON, UniqueConstraint, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

Base = declarative_base()

# OAuth & User Management
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    # Association objects (membership records with role, timestamps, etc.)
    user_companies = relationship("UserCompany", back_populates="user")
    # Convenience many-to-many: list of Company objects the user belongs to
    companies = relationship("Company", secondary="user_companies", back_populates="users")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    usage_logs = relationship("UsageLog", back_populates="user")

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    procore_company_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    # Association objects (membership records with role, timestamps, etc.)
    user_companies = relationship("UserCompany", back_populates="company")
    # Convenience many-to-many: list of User objects in the company
    users = relationship("User", secondary="user_companies", back_populates="companies")
    projects = relationship("Project", back_populates="company")
    procore_connections = relationship("ProcoreConnection", back_populates="company")

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("company_id", "procore_project_id", name="uq_projects_company_procore_id"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # External identifier from Procore (scoped unique per company)
    procore_project_id = Column(String, nullable=False, index=True)
    
    name = Column(String, nullable=False)
    status = Column(String, default="active")  # active, completed, on_hold
    
    # Sync tracking (optional but useful for UI)
    last_sync_at = Column(DateTime, nullable=True)
    sync_status = Column(String, nullable=True)  # idle, syncing, error
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    company = relationship("Company", back_populates="projects")
    jobs = relationship("JobQueue", back_populates="project")
    findings = relationship("Finding", back_populates="project", cascade="all, delete-orphan")

class UserCompany(Base):
    __tablename__ = "user_companies"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    role = Column(String, default="member")  # admin, member, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="user_companies")
    company = relationship("Company", back_populates="user_companies")

class ProcoreConnection(Base):
    __tablename__ = "procore_connections"
    __table_args__ = (
        # 1 row per (company_id, procore_user_id)
        UniqueConstraint(
            "company_id",
            "procore_user_id",
            name="uq_procore_connections_company_user",
        ),

        # Ensure lookups are fast
        Index("ix_procore_connections_procore_user_id", "procore_user_id"),

        # Optional (recommended): enforce only one active company context per Procore user
        # Postgres partial unique index: procore_user_id unique when is_active = true
        Index(
            "uq_procore_connections_active_user",
            "procore_user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)

    # OAuth tokens
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime, nullable=False)

    # NEW: token metadata
    token_type = Column(String, nullable=False, server_default="Bearer")
    scope = Column(Text, nullable=True)

    # Procore details
    procore_user_id = Column(String, nullable=True)  # consider nullable=False once flow always stores after /me

    # NEW: audit (optional but recommended)
    revoked_at = Column(DateTime, nullable=True)  # or disconnected_at if you prefer naming

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company = relationship("Company", back_populates="procore_connections")

# Job Queue
class JobQueue(Base):
    __tablename__ = "job_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    
    job_type = Column(String, nullable=False)  # "drawing_markup", "clash_detection", etc.
    status = Column(String, default="pending")  # pending, processing, completed, failed
    
    # Input/Output references
    input_data = Column(JSON)  # Store drawing IDs, parameters, etc.
    output_url = Column(String)  # S3/object storage URL for result
    
    # Tracking
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    project = relationship("Project", back_populates="jobs")

# Findings (DB term) / Insights (API & UI term)
class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)

    # Scope: every finding belongs to a project
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Mirrors the frontend AIInsight contract
    type = Column(String, nullable=False)       # compliance | deviation | recommendation | warning
    severity = Column(String, nullable=False)   # low | medium | high | critical

    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    # Store list of affected items (MVP)
    affected_items = Column(JSON, default=list)

    resolved = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Optional links (future-proof, can be null for now)
    related_submittal_id = Column(String, nullable=True)
    related_rfi_id = Column(String, nullable=True)
    related_inspection_id = Column(String, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="findings")

# Usage Tracking
class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"))
    
    action = Column(String, nullable=False)  # "drawing_processed", "api_call", etc.
    resource_type = Column(String)  # "drawing", "model", etc.
    
    # Metrics
    processing_time = Column(Float)  # seconds
    cost = Column(Float)  # if tracking costs
    
    # "metadata" is reserved on SQLAlchemy declarative models.
    # Keep the database column name as "metadata", but use a safe Python attribute.
    log_metadata = Column("metadata", JSON)  # Additional data
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    user = relationship("User", back_populates="usage_logs")

# User Settings
class UserSettings(Base):
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Detection settings
    detection_mode = Column(String, default="standard")  # standard, aggressive, conservative
    clash_threshold = Column(Float, default=0.5)  # detection sensitivity
    auto_markup = Column(Boolean, default=True)
    
    # Notification preferences
    email_notifications = Column(Boolean, default=True)
    slack_webhook = Column(String)
    
    # UI preferences
    preferences = Column(JSON)  # Store other custom settings
    
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    user = relationship("User", back_populates="settings")

