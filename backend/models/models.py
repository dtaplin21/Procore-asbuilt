# models/database.py
from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, JSON, UniqueConstraint, Index, text, Date
from sqlalchemy.dialects.postgresql import ARRAY
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
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    company = relationship("Company", back_populates="projects")
    jobs = relationship("JobQueue", back_populates="project")
    findings = relationship("Finding", back_populates="project", cascade="all, delete-orphan")
    drawings = relationship(
        "Drawing",
        back_populates="project",
        foreign_keys="Drawing.project_id",
        cascade="all, delete-orphan",
    )
    evidence_records = relationship("EvidenceRecord", back_populates="project", cascade="all, delete-orphan")
    inspection_runs = relationship("InspectionRun", back_populates="project", cascade="all, delete-orphan")
    master_drawing = relationship(
        "Drawing",
        foreign_keys=[master_drawing_id],
        post_update=True,
    )

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
    # Lifecycle values are plain strings (pending → processing → completed|failed), not Python enums.
    status = Column(String, default="pending")

    # JSON-serializable dict only (ints, bools, str, lists); never ORM instances.
    input_data = Column(JSON)  # e.g. drawing_id, project_id — see services.job_input_data.coerce_job_int
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
    # Relationships
    project = relationship("Project", back_populates="findings")
    drawing = relationship("Drawing", back_populates="findings")

    @property
    def workspace_link(self):
        """Deprecated: use :func:`services.findings.build_finding_workspace_link_metadata` with a DB session."""
        return None

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
    project = relationship("Project", back_populates="drawings", foreign_keys=[project_id])
    renditions = relationship(
        "DrawingRendition",
        back_populates="drawing",
        cascade="all, delete-orphan",
    )
    regions = relationship("DrawingRegion", back_populates="master_drawing", cascade="all, delete-orphan")
    overlays = relationship("DrawingOverlay", back_populates="master_drawing", cascade="all, delete-orphan")
    inspection_runs = relationship("InspectionRun", back_populates="master_drawing", cascade="all, delete-orphan")
    unresolved_evidence = relationship(
        "UnresolvedEvidence",
        back_populates="master_drawing",
        cascade="all, delete-orphan",
    )
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
    """User-defined region on a master drawing (geometry + lookup tags).

    ``inspection_type_tags`` and ``location_tags`` are read by
    ``services.region_index_loader`` to build the ``MasterRegion`` index
    that ``drawing_location_resolver`` matches uploaded evidence against.
    """

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
    # Inspection type(s) for this region, e.g. ["Underground Fire Water Rough In"].
    # Array because a region can be relevant to more than one type over a project.
    inspection_type_tags = Column(
        ARRAY(String),
        nullable=True,
        server_default=text("'{}'::text[]"),
    )
    # Place name(s) for this region, e.g. ["Utility MR", "Level 2"].
    location_tags = Column(
        ARRAY(String),
        nullable=True,
        server_default=text("'{}'::text[]"),
    )

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    master_drawing = relationship("Drawing", back_populates="regions")
    inspection_reviews = relationship("DrawingInspectionReview", back_populates="region")


class DrawingInspectionReview(Base):
    """Human review outcome scoped to an inspection run (optionally a region or overlay).

    ``status``: ``pending`` | ``passed`` | ``failed`` | ``passed_auto`` | ``passed_human``.
    """

    __tablename__ = "drawing_inspection_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','passed','failed','passed_auto','passed_human')",
            name="ck_drawing_inspection_reviews_status",
        ),
        CheckConstraint(
            "inspection_run_id IS NOT NULL",
            name="ck_drawing_inspection_reviews_run_required",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    overlay_id = Column(
        Integer,
        ForeignKey("drawing_overlays.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    region_id = Column(
        Integer,
        ForeignKey("drawing_regions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(16), nullable=False, default="pending", index=True)
    reviewer_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes = Column(Text, nullable=True)
    passed_at = Column(DateTime, nullable=True)

    inspection_run = relationship("InspectionRun", back_populates="inspection_reviews")
    overlay = relationship("DrawingOverlay", back_populates="inspection_reviews")
    region = relationship("DrawingRegion", back_populates="inspection_reviews")


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
    unresolved_evidence = relationship(
        "UnresolvedEvidence",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )
    inspection_reviews = relationship(
        "DrawingInspectionReview",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )


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
    """Overlay on a master drawing from the inspection-mapping pipeline.

    ``created_at`` is when the record was uploaded/created in this system
    (``uploaded_at`` in refactor docs). ``inspection_date`` is when the
    inspection was performed per the source document (nullable when the
    document states no recognizable date).
    """

    __tablename__ = "drawing_overlays"
    __table_args__ = (
        CheckConstraint(
            "status in ('pass','fail','unknown')",
            name="ck_drawing_overlays_status",
        ),
        CheckConstraint(
            "inspection_run_id IS NOT NULL",
            name="ck_drawing_overlays_inspection_run_required",
        ),
        Index("ix_drawing_overlays_master_drawing_id", "master_drawing_id"),
        Index("ix_drawing_overlays_inspection_run_id", "inspection_run_id"),
        Index("ix_drawing_overlays_status", "status"),
        Index("ix_drawing_overlays_master_drawing_id_created_at", "master_drawing_id", "created_at"),
        Index("ix_drawing_overlays_inspection_date", "inspection_date"),
    )

    id = Column(Integer, primary_key=True, index=True)

    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    geometry = Column(JSON, nullable=False)
    status = Column(String, nullable=False, server_default="unknown")  # pass | fail | unknown

    label = Column(String(length=255), nullable=True)
    severity = Column(String(length=32), nullable=True)  # high | medium | info
    confidence_label = Column(String(length=64), nullable=True)
    inspection_date = Column(Date, nullable=True)
    tags_json = Column(JSON, nullable=True)

    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    master_drawing = relationship("Drawing", back_populates="overlays")
    inspection_run = relationship("InspectionRun", back_populates="overlays")
    inspection_reviews = relationship(
        "DrawingInspectionReview",
        back_populates="overlay",
        passive_deletes=True,
    )


class UnresolvedEvidence(Base):
    """Evidence map_document_to_overlays() could not place on the master drawing."""

    __tablename__ = "unresolved_evidence"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(
        Integer,
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason = Column(Text, nullable=False)
    extracted_terms_json = Column(JSON, nullable=False)
    resolved_by_human = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    evidence = relationship("EvidenceRecord", back_populates="unresolved_placements")
    inspection_run = relationship("InspectionRun", back_populates="unresolved_evidence")
    master_drawing = relationship("Drawing", back_populates="unresolved_evidence")


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
    unresolved_placements = relationship(
        "UnresolvedEvidence",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )


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
