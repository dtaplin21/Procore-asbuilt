# models/database.py
from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, JSON, UniqueConstraint, Index, text
from sqlalchemy.sql import func
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
    drawings = relationship("Drawing", back_populates="project", cascade="all, delete-orphan")
    evidence_records = relationship("EvidenceRecord", back_populates="project", cascade="all, delete-orphan")
    inspection_runs = relationship("InspectionRun", back_populates="project", cascade="all, delete-orphan")

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

    # Optional link to a specific drawing (e.g. master drawing where finding was detected)
    drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    drawing_diff_id = Column(
        Integer,
        ForeignKey("drawing_diffs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    project = relationship("Project", back_populates="findings")
    drawing = relationship("Drawing", back_populates="findings")
    drawing_diff = relationship(
        "DrawingDiff",
        foreign_keys=[drawing_diff_id],
    )
    # Diffs that reference this finding (via drawing_diffs.finding_id). Distinct from
    # `drawing_diff` (this row's optional pointer to one diff via findings.drawing_diff_id).
    drawing_diffs = relationship(
        "DrawingDiff",
        back_populates="finding",
        foreign_keys="[DrawingDiff.finding_id]",
        passive_deletes=True,
    )

    @property
    def workspace_link(self):
        """Payload for API workspaceLink (WorkspaceLinkMetadata); None if no drawing/diff context."""
        diff_id = self.drawing_diff_id
        master_id = self.drawing_id
        alignment_id = None
        if diff_id is not None:
            diff = self.drawing_diff
            if diff is not None:
                alignment_id = diff.alignment_id
                if master_id is None and diff.alignment is not None:
                    master_id = diff.alignment.master_drawing_id
        if master_id is None:
            return None
        return {
            "project_id": self.project_id,
            "master_drawing_id": master_id,
            "alignment_id": alignment_id,
            "diff_id": diff_id,
        }

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


# Drawings (uploaded or from Procore)
class Drawing(Base):
    __tablename__ = "drawings"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    
    source = Column(String, nullable=False)  # 'upload' or 'procore'
    name = Column(String, nullable=False)
    storage_key = Column(String, nullable=True)  # path in backend/uploads/ or Procore URL
    file_url = Column(String, nullable=True)  # API endpoint for download
    content_type = Column(String, nullable=True)  # 'application/pdf', 'image/png', etc.
    page_count = Column(Integer, nullable=True)  # for PDFs

    # Rendition processing metadata
    original_filename = Column(String, nullable=True)
    processing_status = Column(String, nullable=False, default="pending")  # pending, processing, ready, failed
    processing_error = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    project = relationship("Project", back_populates="drawings")
    renditions = relationship(
        "DrawingRendition",
        back_populates="drawing",
        cascade="all, delete-orphan",
    )
    regions = relationship("DrawingRegion", back_populates="master_drawing", cascade="all, delete-orphan")
    overlays = relationship("DrawingOverlay", back_populates="master_drawing", cascade="all, delete-orphan")
    alignments_as_master = relationship(
        "DrawingAlignment",
        foreign_keys="DrawingAlignment.master_drawing_id",
        back_populates="master_drawing",
        cascade="all, delete-orphan",
    )
    alignments_as_sub = relationship(
        "DrawingAlignment",
        foreign_keys="DrawingAlignment.sub_drawing_id",
        back_populates="sub_drawing",
        cascade="all, delete-orphan",
    )
    inspection_runs = relationship("InspectionRun", back_populates="master_drawing", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="drawing")


class DrawingRendition(Base):
    """Rendered image page for a drawing (e.g. PNG from PDF)."""
    __tablename__ = "drawing_renditions"
    __table_args__ = (
        UniqueConstraint("drawing_id", "page_number", name="uq_drawing_renditions_drawing_page"),
    )

    id = Column(Integer, primary_key=True, index=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)  # 1-based page number

    image_storage_key = Column(String, nullable=False)
    mime_type = Column(String, nullable=False, default="image/png")
    width_px = Column(Integer, nullable=True)
    height_px = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)

    render_status = Column(String, nullable=False, default="ready")  # ready | failed
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    drawing = relationship("Drawing", back_populates="renditions")


class DrawingRegion(Base):
    __tablename__ = "drawing_regions"

    id = Column(Integer, primary_key=True, index=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(length=255), nullable=False)
    page = Column(Integer, nullable=False, default=1)
    geometry = Column(JSON, nullable=False)  # normalized 0-1; rect or polygon

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    master_drawing = relationship("Drawing", back_populates="regions")
    alignments = relationship("DrawingAlignment", back_populates="region")


class DrawingAlignment(Base):
    __tablename__ = "drawing_alignments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sub_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region_id = Column(
        Integer,
        ForeignKey("drawing_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    method = Column(String(length=50), nullable=False)  # manual | feature_match | vision
    transform = Column(JSON, nullable=True)  # homography/affine + confidence
    status = Column(String(length=50), nullable=False)  # queued | processing | complete | failed
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    master_drawing = relationship(
        "Drawing",
        foreign_keys=[master_drawing_id],
        back_populates="alignments_as_master",
    )
    sub_drawing = relationship(
        "Drawing",
        foreign_keys=[sub_drawing_id],
        back_populates="alignments_as_sub",
    )
    region = relationship("DrawingRegion", back_populates="alignments")
    drawing_diffs = relationship("DrawingDiff", back_populates="alignment", cascade="all, delete-orphan")


class DrawingDiff(Base):
    """Diff analysis between master and sub drawing; optionally linked to a finding."""
    __tablename__ = "drawing_diffs"

    id = Column(Integer, primary_key=True, index=True)
    alignment_id = Column(
        Integer,
        ForeignKey("drawing_alignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id = Column(
        Integer,
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary = Column(String, nullable=False)
    severity = Column(String, nullable=False, index=True)  # low | medium | high | critical
    diff_regions = Column(JSON, nullable=False)  # list of normalized region objects

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    alignment = relationship("DrawingAlignment", back_populates="drawing_diffs")
    finding = relationship(
        "Finding",
        back_populates="drawing_diffs",
        foreign_keys=[finding_id],
    )
    overlays = relationship("DrawingOverlay", back_populates="diff", passive_deletes=True)


# Inspection runs (AI extraction from evidence docs)
class InspectionRun(Base):
    __tablename__ = "inspection_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','processing','complete','failed')",
            name="ck_inspection_runs_status",
        ),
        Index("ix_inspection_runs_project_id", "project_id"),
        Index("ix_inspection_runs_master_drawing_id", "master_drawing_id"),
        Index("ix_inspection_runs_evidence_id", "evidence_id"),
        Index("ix_inspection_runs_status", "status"),
        Index("ix_inspection_runs_project_id_created_at", "project_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id = Column(
        Integer,
        ForeignKey("evidence_records.id", ondelete="SET NULL"),
        nullable=True,
    )

    inspection_type = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="queued")  # queued | processing | complete | failed

    # Procore sync: set after successful inspection writeback (commit) for item-level writeback
    procore_inspection_id = Column(String, nullable=True, index=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="inspection_runs")
    master_drawing = relationship("Drawing", back_populates="inspection_runs")
    evidence = relationship("EvidenceRecord", back_populates="inspection_runs")
    results = relationship("InspectionResult", back_populates="inspection_run", cascade="all, delete-orphan")
    overlays = relationship("DrawingOverlay", back_populates="inspection_run", passive_deletes=True)


class InspectionResult(Base):
    __tablename__ = "inspection_results"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('pass','fail','mixed','unknown')",
            name="ck_inspection_results_outcome",
        ),
        Index("ix_inspection_results_inspection_run_id", "inspection_run_id"),
        Index("ix_inspection_results_outcome", "outcome"),
        Index("ix_inspection_results_inspection_run_id_created_at", "inspection_run_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    outcome = Column(String, nullable=False, server_default="unknown")  # pass | fail | mixed | unknown
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    inspection_run = relationship("InspectionRun", back_populates="results")


class DrawingOverlay(Base):
    """Overlay geometry on a master drawing; sourced from either an inspection run or a drawing diff."""
    __tablename__ = "drawing_overlays"
    __table_args__ = (
        CheckConstraint(
            "status in ('pass','fail','unknown')",
            name="ck_drawing_overlays_status",
        ),
        CheckConstraint(
            "(inspection_run_id is not null)::int + (diff_id is not null)::int = 1",
            name="ck_drawing_overlays_exactly_one_source",
        ),
        Index("ix_drawing_overlays_master_drawing_id", "master_drawing_id"),
        Index("ix_drawing_overlays_inspection_run_id", "inspection_run_id"),
        Index("ix_drawing_overlays_diff_id", "diff_id"),
        Index("ix_drawing_overlays_status", "status"),
        Index("ix_drawing_overlays_master_drawing_id_created_at", "master_drawing_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff_id = Column(
        Integer,
        ForeignKey("drawing_diffs.id", ondelete="SET NULL"),
        nullable=True,
    )

    geometry = Column(JSON, nullable=False)
    status = Column(String, nullable=False, server_default="unknown")  # pass | fail | unknown

    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    master_drawing = relationship("Drawing", back_populates="overlays")
    inspection_run = relationship("InspectionRun", back_populates="overlays")
    diff = relationship("DrawingDiff", back_populates="overlays")


# Evidence Records (specs, inspection docs, etc.)
class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        Index("ix_evidence_records_project_type", "project_id", "type"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    
    type = Column(String(50), nullable=False)  # 'spec' or 'inspection_doc'
    trade = Column(String, nullable=True)  # e.g., 'HVAC', 'Electrical'
    spec_section = Column(String, nullable=True)  # e.g., '15830 - HVAC Controls'
    title = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="new")
    source_id = Column(String(255), nullable=True)
    storage_key = Column(String, nullable=True)  # path in backend/uploads/
    content_type = Column(String, nullable=True)  # 'application/pdf', 'image/png', etc.
    text_content = Column(Text, nullable=True)  # Phase 4: extracted text from PDFs
    dates = Column(JSON, nullable=True)
    attachments_json = Column(JSON, nullable=True)
    cross_refs_json = Column(JSON, nullable=True)
    
    # Flexible metadata for future extensions
    meta = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    project = relationship("Project", back_populates="evidence_records")
    inspection_runs = relationship("InspectionRun", back_populates="evidence")


class EvidenceDrawingLink(Base):
    __tablename__ = "evidence_drawing_links"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence_records.id"), nullable=False, index=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id"), nullable=False, index=True)

    link_type = Column(String(50), nullable=False, default="sheet_ref")
    matched_text = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    source = Column(String(50), nullable=False, default="regex")
    is_primary = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", backref="evidence_drawing_links")
    evidence = relationship("EvidenceRecord", backref="drawing_links")
    drawing = relationship("Drawing", backref="evidence_links")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
        Index("ix_idempotency_keys_scope_status", "scope", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="in_progress")
    response_payload = Column(JSON, nullable=True)
    resource_reference = Column(JSON, nullable=True)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class ProcoreWriteback(Base):
    __tablename__ = "procore_writebacks"
    __table_args__ = (
        Index("ix_procore_writebacks_project_created", "project_id", "created_at"),
        Index("ix_procore_writebacks_run", "inspection_run_id"),
        Index("ix_procore_writebacks_finding", "finding_id"),
        Index("ix_procore_writebacks_type_status", "writeback_type", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    inspection_run_id = Column(Integer, ForeignKey("inspection_runs.id", ondelete="SET NULL"), nullable=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    writeback_type = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="queued")
    payload = Column(JSON, nullable=True)
    procore_response = Column(JSON, nullable=True)
    resource_reference = Column(JSON, nullable=True)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
