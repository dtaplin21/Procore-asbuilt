"""
Storage service.

This project previously had table-backed demo endpoints (projects/submittals/rfis/etc).
Those ORM models and schemas have been removed. We keep this service as a placeholder
so routes can continue to import it while the new data model is designed.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session, joinedload

# ---------------------------------------------------------------------------
# Rendered page image storage helpers (local storage, storage-key-based)
# ---------------------------------------------------------------------------

UPLOAD_ROOT = Path(__file__).parent.parent / "uploads"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_drawing_source_storage_key(project_id: int, drawing_id: int, filename: str) -> str:
    return f"drawings/source/project-{project_id}/drawing-{drawing_id}/{filename}"


def build_drawing_render_storage_key(project_id: int, drawing_id: int, page_number: int) -> str:
    return f"drawings/rendered/project-{project_id}/drawing-{drawing_id}/page-{page_number}.png"


def storage_key_to_abs_path(storage_key: str) -> Path:
    return UPLOAD_ROOT / storage_key


def write_bytes_to_storage_key(storage_key: str, data: bytes) -> Path:
    abs_path = storage_key_to_abs_path(storage_key)
    ensure_parent_dir(abs_path)
    abs_path.write_bytes(data)
    return abs_path


def get_storage_file_size(storage_key: str) -> int | None:
    abs_path = storage_key_to_abs_path(storage_key)
    if not abs_path.exists():
        return None
    return abs_path.stat().st_size


def open_storage_path(storage_key: str) -> Path:
    return storage_key_to_abs_path(storage_key)
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List, Optional, Sequence, Set, cast

from models.models import (
    Project,
    Finding,
    JobQueue,
    Drawing,
    DrawingRegion,
    DrawingAlignment,
    DrawingDiff,
    DrawingRendition,
    EvidenceRecord,
    EvidenceDrawingLink,
    UsageLog,
    InspectionRun,
    InspectionResult,
    DrawingOverlay,
    ProcoreWriteback,
)
from services.procore_connection_store import get_active_connection
from services.evidence_linking import replace_evidence_drawing_links


class StorageService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Placeholder methods (return empty data until new models are defined)
    # ------------------------------------------------------------------

    def get_projects(
        self,
        company_id: Optional[int] = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Project], int]:
        """List projects with pagination. Returns (items, total)."""
        q = self.db.query(Project)
        if company_id is not None:
            q = q.filter(Project.company_id == company_id)
        base = q.order_by(Project.name.asc())
        total = base.count()
        items = base.limit(limit).offset(offset).all()
        return items, total

    def get_project(self, project_id: int) -> Optional[Project]:
        return self.db.query(Project).filter(Project.id == project_id).first()

    def get_project_dashboard_summary(
        self,
        project_id: int,
        procore_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        project = self.get_project(project_id)
        if project is None:
            return {}

        conn = None
        if procore_user_id:
            conn = get_active_connection(self.db, procore_user_id)

        connected = conn is not None
        active_company_id = conn.company_id if conn is not None else None
        project_company_id = cast(int, project.company_id)
        matches_active_company = bool(active_company_id == project_company_id) if active_company_id is not None else False

        # KPIs
        total_findings = self.db.query(Finding).filter(Finding.project_id == project_id).count()
        open_findings = self.db.query(Finding).filter(
            Finding.project_id == project_id,
            Finding.resolved.is_(False),
        ).count()
        drawings_count = self.db.query(Drawing).filter(Drawing.project_id == project_id).count()
        evidence_count = self.db.query(EvidenceRecord).filter(EvidenceRecord.project_id == project_id).count()
        inspections_count = self.db.query(InspectionRun).filter(InspectionRun.project_id == project_id).count()

        # NOTE: Return datetimes as datetime objects. If the route uses a Pydantic response_model
        # (recommended), FastAPI will serialize these. If returning raw dict without a model,
        # you may want to .isoformat() them instead.
        return {
            "project": {
                "id": cast(int, project.id),
                "name": project.name,
                "company_id": project_company_id,
                "procore_project_id": getattr(project, "procore_project_id", None),
            },
            "company_context": {
                "active_company_id": active_company_id,
                "project_company_id": project_company_id,
                "matches_active_company": matches_active_company,
            },
            "sync_health": {
                "connected": connected,
                "sync_status": getattr(project, "sync_status", None) or "idle",
                "project_last_sync_at": getattr(project, "last_sync_at", None),
                "token_expires_at": getattr(conn, "token_expires_at", None) if conn is not None else None,
                "error_message": None if connected else ("Not connected to Procore" if procore_user_id else None),
            },
            "current_drawing": None,
            "kpis": {
                "total_findings": total_findings,
                "open_findings": open_findings,
                "drawings_count": drawings_count,
                "evidence_count": evidence_count,
                "inspections_count": inspections_count,
            },
        }
    
    def get_project_jobs(
        self,
        project_id: int,
        status: Optional[str] = None,
    ) -> List[JobQueue]:
        q = self.db.query(JobQueue).filter(JobQueue.project_id == project_id)

        if status == "active":
            q = q.filter(JobQueue.status.in_(["queued", "running", "processing"]))
        elif status is not None:
            q = q.filter(JobQueue.status == status)

        q = q.order_by(JobQueue.updated_at.desc(), JobQueue.id.desc())
        return q.all()
    
        # ------------------------------------------------------------------
    # Drawings (Phase 1)
    # ------------------------------------------------------------------

    def create_drawing(
        self,
        project_id: int,
        *,
        source: str,
        name: str,
        storage_key: str,
        content_type: str,
        page_count: Optional[int] = None,
    ) -> Drawing:
        drawing = Drawing(
            project_id=project_id,
            source=source,
            name=name,
            storage_key=storage_key,
            content_type=content_type,
            page_count=page_count,
        )
        self.db.add(drawing)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(drawing)
        return drawing

    def list_drawings(self, project_id: int) -> List[Drawing]:
        return (
            self.db.query(Drawing)
            .filter(Drawing.project_id == project_id)
            .order_by(Drawing.created_at.desc(), Drawing.id.desc())
            .all()
        )

    def list_drawings_by_project(self, project_id: int) -> List[Drawing]:
        """List drawings for a project, newest-first. Stable ordering for selection UIs."""
        return (
            self.db.query(Drawing)
            .filter(Drawing.project_id == project_id)
            .order_by(Drawing.created_at.desc(), Drawing.id.desc())
            .all()
        )

    def get_drawing(self, project_id: int, drawing_id: int) -> Optional[Drawing]:
        return (
            self.db.query(Drawing)
            .filter(Drawing.project_id == project_id, Drawing.id == drawing_id)
            .first()
        )

    def get_drawing_by_id(self, drawing_id: int) -> Optional[Drawing]:
        """Get a drawing by ID only (no project scope)."""
        return self.db.query(Drawing).filter(Drawing.id == drawing_id).first()

    def set_drawing_processing_status(
        self,
        drawing_id: int,
        status: str,
        error: Optional[str] = None,
        page_count: Optional[int] = None,
    ) -> Drawing:
        drawing = self.get_drawing_by_id(drawing_id)
        if not drawing:
            raise ValueError(f"Drawing {drawing_id} not found")

        drawing.processing_status = status
        drawing.processing_error = error
        if page_count is not None:
            drawing.page_count = page_count

        self.db.add(drawing)
        self.db.commit()
        self.db.refresh(drawing)
        return drawing

    def upsert_drawing_rendition(
        self,
        drawing_id: int,
        page_number: int,
        image_storage_key: str,
        mime_type: str,
        width_px: Optional[int],
        height_px: Optional[int],
        file_size: Optional[int],
        render_status: str = "ready",
        error_message: Optional[str] = None,
    ) -> DrawingRendition:
        rendition = (
            self.db.query(DrawingRendition)
            .filter(
                DrawingRendition.drawing_id == drawing_id,
                DrawingRendition.page_number == page_number,
            )
            .first()
        )

        if rendition is None:
            rendition = DrawingRendition(
                drawing_id=drawing_id,
                page_number=page_number,
            )

        rendition.image_storage_key = image_storage_key
        rendition.mime_type = mime_type
        rendition.width_px = width_px
        rendition.height_px = height_px
        rendition.file_size = file_size
        rendition.render_status = render_status
        rendition.error_message = error_message

        self.db.add(rendition)
        self.db.commit()
        self.db.refresh(rendition)
        return rendition

    def get_drawing_rendition(
        self, drawing_id: int, page_number: int
    ) -> Optional[DrawingRendition]:
        return (
            self.db.query(DrawingRendition)
            .filter(
                DrawingRendition.drawing_id == drawing_id,
                DrawingRendition.page_number == page_number,
                DrawingRendition.render_status == "ready",
            )
            .first()
        )

    def list_drawing_renditions(self, drawing_id: int) -> List[DrawingRendition]:
        return (
            self.db.query(DrawingRendition)
            .filter(DrawingRendition.drawing_id == drawing_id)
            .order_by(DrawingRendition.page_number.asc())
            .all()
        )

    # ------------------------------------------------------------------
    # Drawing Regions (Phase 2)
    # ------------------------------------------------------------------

    def create_drawing_region(
        self,
        master_drawing_id: int,
        *,
        label: str,
        page: int = 1,
        geometry: Dict[str, Any],
    ) -> DrawingRegion:
        region = DrawingRegion(
            master_drawing_id=master_drawing_id,
            label=label,
            page=page,
            geometry=geometry,
        )
        self.db.add(region)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(region)
        return region

    def list_drawing_regions(self, master_drawing_id: int) -> List[DrawingRegion]:
        return (
            self.db.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == master_drawing_id)
            .order_by(DrawingRegion.created_at.desc(), DrawingRegion.id.desc())
            .all()
        )

    def get_drawing_region(
        self,
        master_drawing_id: int,
        region_id: int,
    ) -> Optional[DrawingRegion]:
        return (
            self.db.query(DrawingRegion)
            .filter(
                DrawingRegion.master_drawing_id == master_drawing_id,
                DrawingRegion.id == region_id,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # Drawing Alignments (Phase 2)
    # ------------------------------------------------------------------

    IDENTITY_TRANSFORM: Dict[str, Any] = {
        "type": "identity",
        "matrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "confidence": 0.0,
        "residual_error": None,
        "page": 1,
    }

    def create_drawing_alignment(
        self,
        master_drawing_id: int,
        sub_drawing_id: int,
        method: str,
        *,
        region_id: Optional[int] = None,
    ) -> DrawingAlignment:
        """
        Create alignment row. Lifecycle status:
        - manual: complete immediately with identity transform
        - feature_match | vision: queued (caller runs pipeline -> processing -> complete/failed)
        """
        if method.strip().lower() == "manual":
            status = "complete"
            transform = self.IDENTITY_TRANSFORM
        else:
            status = "queued"
            transform = None

        master = (
            self.db.query(Drawing)
            .filter(Drawing.id == master_drawing_id)
            .first()
        )
        if master is None:
            raise ValueError(f"Master drawing {master_drawing_id} not found")
        sub = self.db.query(Drawing).filter(Drawing.id == sub_drawing_id).first()
        if sub is None:
            raise ValueError(f"Sub drawing {sub_drawing_id} not found")
        if sub.project_id != master.project_id:
            raise ValueError(
                "Master and sub drawings must belong to the same project"
            )

        alignment = DrawingAlignment(
            project_id=master.project_id,
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
            region_id=region_id,
            method=method,
            status=status,
            transform=transform,
        )
        self.db.add(alignment)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(alignment)
        return alignment

    def create_drawing_alignment_with_transform(
        self,
        project_id: int,
        master_drawing_id: int,
        sub_drawing_id: int,
        transform_matrix: Dict[str, Any],
        alignment_status: str = "manual_mvp",
        *,
        region_id: Optional[int] = None,
    ) -> DrawingAlignment:
        """
        Create alignment with explicit transform and status.
        project_id is used for validation (drawings must belong to project).
        Maps transform_matrix -> transform, alignment_status -> status.
        """
        if self.get_drawing(project_id, master_drawing_id) is None:
            raise ValueError(f"Master drawing {master_drawing_id} not found in project")
        if self.get_drawing(project_id, sub_drawing_id) is None:
            raise ValueError(f"Sub drawing {sub_drawing_id} not found in project")

        method = "manual"
        alignment = DrawingAlignment(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
            region_id=region_id,
            method=method,
            status=alignment_status,
            transform=transform_matrix,
        )
        self.db.add(alignment)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(alignment)
        return alignment

    def list_drawing_alignments(
        self,
        master_drawing_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[DrawingAlignment], int]:
        """List alignments for a master drawing with pagination. Returns (items, total)."""
        base = (
            self.db.query(DrawingAlignment)
            .filter(DrawingAlignment.master_drawing_id == master_drawing_id)
            .order_by(DrawingAlignment.created_at.desc(), DrawingAlignment.id.desc())
        )
        total = base.count()
        items = base.limit(limit).offset(offset).all()
        return items, total

    def get_drawing_alignment_by_id(
        self,
        project_id: int,
        master_drawing_id: int,
        alignment_id: int,
    ) -> Optional[DrawingAlignment]:
        """
        Fetch alignment with project validation.
        Ensures: alignment exists, belongs to correct project, belongs to correct master drawing.
        """
        alignment = (
            self.db.query(DrawingAlignment)
            .filter(
                DrawingAlignment.id == alignment_id,
                DrawingAlignment.master_drawing_id == master_drawing_id,
                DrawingAlignment.project_id == project_id,
            )
            .first()
        )
        if alignment is None:
            return None
        if self.get_drawing(project_id, master_drawing_id) is None:
            return None
        return alignment

    def get_alignment_by_drawing_pair(
        self,
        master_drawing_id: int,
        sub_drawing_id: int,
        project_id: Optional[int] = None,
    ) -> Optional[DrawingAlignment]:
        """
        Get alignment for a master/sub drawing pair.
        If project_id is provided, validates master drawing belongs to project.
        """
        base = (
            self.db.query(DrawingAlignment)
            .filter(
                DrawingAlignment.master_drawing_id == master_drawing_id,
                DrawingAlignment.sub_drawing_id == sub_drawing_id,
            )
        )
        if project_id is not None:
            base = base.join(Drawing, DrawingAlignment.master_drawing_id == Drawing.id).filter(
                Drawing.project_id == project_id
            )
        return (
            base.order_by(DrawingAlignment.updated_at.desc(), DrawingAlignment.id.desc())
            .first()
        )

    def list_alignments_by_master_drawing(
        self,
        project_id: int,
        master_drawing_id: int,
    ):
        """List alignments for a master drawing, sorted by created_at desc (history view)."""
        return (
            self.db.query(DrawingAlignment)
            .join(Drawing, DrawingAlignment.master_drawing_id == Drawing.id)
            .options(
                joinedload(DrawingAlignment.master_drawing),
                joinedload(DrawingAlignment.sub_drawing),
            )
            .filter(
                Drawing.project_id == project_id,
                DrawingAlignment.master_drawing_id == master_drawing_id,
            )
            .order_by(DrawingAlignment.created_at.desc())
            .all()
        )

    def get_reusable_alignment(
        self,
        master_drawing_id: int,
        sub_drawing_id: int,
    ) -> Optional[DrawingAlignment]:
        """
        Return alignment with a valid transform if one exists.
        Reusable = status complete and transform present with matrix.
        """
        alignment = self.get_alignment_by_drawing_pair(
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
        )
        if alignment is None:
            return None
        transform = getattr(alignment, "transform", None)
        if not transform or not transform.get("matrix"):
            return None
        status = getattr(alignment, "status", "")
        if status != "complete":
            return None
        return alignment

    def update_alignment_status(
        self,
        alignment_id: int,
        status: str,
        *,
        transform: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[DrawingAlignment]:
        alignment = self.db.query(DrawingAlignment).filter(DrawingAlignment.id == alignment_id).first()
        if alignment is None:
            return None

        setattr(alignment, "status", status)
        if transform is not None:
            setattr(alignment, "transform", transform)
        if error_message is not None:
            setattr(alignment, "error_message", error_message)

        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(alignment)
        return alignment

    # ------------------------------------------------------------------
    # Drawing Diffs
    # ------------------------------------------------------------------

    def create_drawing_diff(
        self,
        alignment_id: int,
        *,
        summary: str,
        severity: str,
        diff_regions: List[Dict[str, Any]],
        finding_id: Optional[int] = None,
    ) -> DrawingDiff:
        diff = DrawingDiff(
            alignment_id=alignment_id,
            finding_id=finding_id,
            summary=summary,
            severity=severity,
            diff_regions=diff_regions,
        )
        self.db.add(diff)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(diff)
        return diff

    def list_drawing_diffs(
        self,
        master_drawing_id: int,
        *,
        alignment_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[DrawingDiff], int]:
        """
        List diffs for a master drawing, optionally filtered by alignment.
        Sorted by created_at desc. Returns (items, total).
        """
        base = (
            self.db.query(DrawingDiff)
            .join(DrawingAlignment, DrawingDiff.alignment_id == DrawingAlignment.id)
            .filter(DrawingAlignment.master_drawing_id == master_drawing_id)
        )
        if alignment_id is not None:
            base = base.filter(DrawingDiff.alignment_id == alignment_id)
        total = base.count()
        items = (
            base.order_by(DrawingDiff.created_at.desc(), DrawingDiff.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return items, total

    def list_drawing_diffs_by_alignment(self, alignment_id: int) -> List[DrawingDiff]:
        return (
            self.db.query(DrawingDiff)
            .filter(DrawingDiff.alignment_id == alignment_id)
            .order_by(DrawingDiff.created_at.asc())
            .all()
        )

    def list_diffs_for_master_drawing(
        self,
        project_id: int,
        master_drawing_id: int,
        alignment_id: int | None = None,
    ):
        """List diffs for a master drawing, optionally filtered by alignment. Ensures diffs belong to the given project."""
        query = (
            self.db.query(DrawingDiff)
            .join(DrawingAlignment, DrawingDiff.alignment_id == DrawingAlignment.id)
            .join(Drawing, DrawingAlignment.master_drawing_id == Drawing.id)
            .filter(
                Drawing.project_id == project_id,
                DrawingAlignment.master_drawing_id == master_drawing_id,
            )
        )

        if alignment_id is not None:
            query = query.filter(DrawingAlignment.id == alignment_id)

        return query.order_by(DrawingDiff.created_at.desc()).all()

    def get_drawing_diff(
        self,
        alignment_id: int,
        diff_id: int,
    ) -> Optional[DrawingDiff]:
        return (
            self.db.query(DrawingDiff)
            .filter(
                DrawingDiff.alignment_id == alignment_id,
                DrawingDiff.id == diff_id,
            )
            .first()
        )

    SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def create_finding_for_diff(
        self,
        diff: DrawingDiff,
        *,
        severity_threshold: str = "high",
        finding_type: str = "deviation",
        idempotency_key: Optional[str] = None,
    ) -> Optional[Finding]:
        """
        When diff severity exceeds threshold, create a Finding and attach finding_id to diff.
        Returns the Finding if created, else None.
        Finding fields: type="deviation", title="Mismatch on {drawing.name}", description=summary,
        affected_items=region labels, project_id=master drawing project.
        """
        diff_severity = cast(str, diff.severity)
        sev_rank = self.SEVERITY_ORDER.get(diff_severity, 0)
        thresh_rank = self.SEVERITY_ORDER.get(severity_threshold, 3)  # default "high"
        if sev_rank < thresh_rank:
            return None

        alignment = self.db.query(DrawingAlignment).filter(
            DrawingAlignment.id == diff.alignment_id,
        ).first()
        if alignment is None:
            return None
        master = self.db.query(Drawing).filter(
            Drawing.id == cast(int, alignment.master_drawing_id),
        ).first()
        if master is None:
            return None
        project_id = cast(int, master.project_id)
        drawing_name = getattr(master, "name", "drawing") or "drawing"

        # Extract region labels from diff_regions for affected_items
        regions = diff.diff_regions if isinstance(diff.diff_regions, list) else []
        affected_items = [
            r.get("label") for r in regions
            if isinstance(r, dict) and r.get("label")
        ]

        master_drawing_id = cast(int, master.id)
        finding = Finding(
            project_id=project_id,
            drawing_id=master_drawing_id,
            type=finding_type,
            severity=diff_severity,
            title=f"Mismatch on {drawing_name}",
            description=diff.summary,
            affected_items=affected_items,
        )
        self.db.add(finding)
        try:
            self.db.flush()  # get finding.id
            setattr(diff, "finding_id", cast(int, finding.id))
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(finding)
        self.db.refresh(diff)
        return finding

    def create_finding(
        self,
        project_id: int,
        *,
        type: str = "deviation",
        severity: str = "high",
        title: str,
        description: str,
        affected_items: Optional[List[str]] = None,
        drawing_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Finding:
        """Create a Finding (used by inspection pipeline, etc.)."""
        finding = Finding(
            project_id=project_id,
            type=type,
            severity=severity,
            title=title,
            description=description,
            affected_items=affected_items or [],
            drawing_id=drawing_id,
        )
        self.db.add(finding)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(finding)
        return finding

    # ------------------------------------------------------------------
    # Evidence Records
    # ------------------------------------------------------------------

    def create_evidence_record(
        self,
        project_id: int,
        *,
        type: str,  # "spec" | "inspection_doc"
        title: str,
        storage_key: str,
        content_type: str,
        trade: Optional[str] = None,
        spec_section: Optional[str] = None,
        text_content: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> EvidenceRecord:
        record = EvidenceRecord(
            project_id=project_id,
            type=type,
            trade=trade,
            spec_section=spec_section,
            title=title,
            storage_key=storage_key,
            content_type=content_type,
            text_content=text_content,
            meta=meta or {},
        )
        self.db.add(record)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(record)
        return record

    def list_evidence_records(
        self,
        project_id: int,
        *,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[EvidenceRecord], int]:
        """List evidence records with pagination. Returns (items, total)."""
        q = self.db.query(EvidenceRecord).filter(EvidenceRecord.project_id == project_id)
        if type is not None:
            q = q.filter(EvidenceRecord.type == type)
        base = q.order_by(EvidenceRecord.created_at.desc(), EvidenceRecord.id.desc())
        total = base.count()
        items = base.limit(limit).offset(offset).all()
        return items, total

    def get_evidence_record(self, project_id: int, evidence_id: int) -> Optional[EvidenceRecord]:
        return (
            self.db.query(EvidenceRecord)
            .filter(EvidenceRecord.project_id == project_id, EvidenceRecord.id == evidence_id)
            .first()
        )

    def create_evidence_record_from_data(
        self,
        project_id: int,
        data: dict,
    ) -> EvidenceRecord:
        """Create evidence record from a dict (type, title, status, etc.)."""
        record = EvidenceRecord(
            project_id=project_id,
            type=data["type"],
            title=data["title"],
            status=data.get("status", "new"),
            source_id=data.get("source_id"),
            text_content=data.get("text_content"),
            dates=data.get("dates"),
            attachments_json=data.get("attachments_json"),
            cross_refs_json=data.get("cross_refs_json"),
        )
        self.db.add(record)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(record)
        return record

    def update_evidence_record(
        self,
        project_id: int,
        evidence_id: int,
        updates: dict,
    ) -> Optional[EvidenceRecord]:
        record = self.get_evidence_record(project_id, evidence_id)
        if record is None:
            return None

        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)

        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        self.db.refresh(record)
        return record

    def relink_evidence_to_drawings(
        self,
        project_id: int,
        evidence_id: int,
    ) -> List[EvidenceDrawingLink]:
        record = self.get_evidence_record(project_id=project_id, evidence_id=evidence_id)
        if record is None:
            return []
        return replace_evidence_drawing_links(self.db, record)

    def list_evidence_drawing_links(
        self,
        project_id: int,
        evidence_id: int,
    ) -> List[EvidenceDrawingLink]:
        return (
            self.db.query(EvidenceDrawingLink)
            .filter(
                EvidenceDrawingLink.project_id == project_id,
                EvidenceDrawingLink.evidence_id == evidence_id,
            )
            .order_by(EvidenceDrawingLink.id.asc())
            .all()
        )

    def create_manual_evidence_drawing_link(
        self,
        project_id: int,
        evidence_id: int,
        *,
        drawing_id: int,
        link_type: str = "manual",
        matched_text: Optional[str] = None,
        confidence: Optional[float] = None,
        source: str = "manual",
        is_primary: bool = False,
    ) -> EvidenceDrawingLink:
        link = EvidenceDrawingLink(
            project_id=project_id,
            evidence_id=evidence_id,
            drawing_id=drawing_id,
            link_type=link_type,
            matched_text=matched_text,
            confidence=confidence,
            source=source,
            is_primary=is_primary,
        )
        self.db.add(link)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(link)
        return link

    def delete_evidence_record(
        self,
        project_id: int,
        evidence_id: int,
    ) -> bool:
        record = self.get_evidence_record(project_id, evidence_id)
        if record is None:
            return False

        try:
            self.db.delete(record)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return True

    def upsert_rfi_evidence_record(
        self,
        project_id: int,
        *,
        source_id: str,
        title: str,
        status: str,
        text_content: Optional[str] = None,
        dates: Optional[Dict[str, Any]] = None,
        attachments_json: Optional[List[Any]] = None,
        cross_refs_json: Optional[List[Any]] = None,
    ) -> EvidenceRecord:
        record = (
            self.db.query(EvidenceRecord)
            .filter(
                EvidenceRecord.project_id == project_id,
                EvidenceRecord.type == "rfi",
                EvidenceRecord.source_id == source_id,
            )
            .first()
        )

        if record is None:
            record = EvidenceRecord(
                project_id=project_id,
                type="rfi",
                source_id=source_id,
            )
            self.db.add(record)

        setattr(record, "title", title)
        setattr(record, "status", status)
        setattr(record, "text_content", text_content)
        setattr(record, "dates", dates or {})
        setattr(record, "attachments_json", attachments_json or [])
        setattr(record, "cross_refs_json", cross_refs_json or [])

        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Inspection Runs
    # ------------------------------------------------------------------

    def create_inspection_run(
        self,
        project_id: int,
        master_drawing_id: int,
        evidence_id: Optional[int] = None,
        inspection_type: Optional[str] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> InspectionRun:
        run = InspectionRun(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            evidence_id=evidence_id,
            inspection_type=inspection_type,
            status="queued",
        )
        self.db.add(run)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(run)
        return run

    def get_inspection_run(self, project_id: int, run_id: int) -> Optional[InspectionRun]:
        return (
            self.db.query(InspectionRun)
            .filter(InspectionRun.project_id == project_id, InspectionRun.id == run_id)
            .first()
        )

    def list_inspection_runs(
        self,
        project_id: int,
        *,
        master_drawing_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[InspectionRun], int]:
        """List inspection runs with pagination. Returns (items, total)."""
        q = self.db.query(InspectionRun).filter(InspectionRun.project_id == project_id)
        if master_drawing_id is not None:
            q = q.filter(InspectionRun.master_drawing_id == master_drawing_id)
        if status is not None:
            q = q.filter(InspectionRun.status == status)
        base = q.order_by(InspectionRun.created_at.desc(), InspectionRun.id.desc())
        total = base.count()
        items = base.limit(limit).offset(offset).all()
        return items, total

    def update_inspection_run_status(
        self,
        run_id: int,
        status: str,
        *,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        inspection_type: Optional[str] = None,
    ) -> Optional[InspectionRun]:
        run = self.db.query(InspectionRun).filter(InspectionRun.id == run_id).first()
        if run is None:
            return None

        setattr(run, "status", status)
        if started_at is not None:
            setattr(run, "started_at", started_at)
        if completed_at is not None:
            setattr(run, "completed_at", completed_at)
        if error_message is not None:
            setattr(run, "error_message", error_message)
        if inspection_type is not None:
            setattr(run, "inspection_type", inspection_type)

        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(run)
        return run

    def get_inspection_run_with_details(
        self,
        project_id: int,
        inspection_run_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Convenience helper for builder/writeback flows.

        Returns dict with:
          - run: InspectionRun
          - project: Project (validated)
          - master_drawing: Drawing
          - evidence: EvidenceRecord | None
          - inspection_result: latest InspectionResult | None
          - overlays: List[DrawingOverlay] filtered to this run
          - findings: List[Finding] linked via overlays/diffs
        """
        run = self.get_inspection_run(project_id, inspection_run_id)
        if run is None:
            return None

        project = self.get_project(project_id)
        if project is None:
            return None

        master_drawing = (
            self.db.query(Drawing)
            .filter(Drawing.id == cast(int, run.master_drawing_id))
            .first()
        )
        if master_drawing is None:
            return None

        evidence: Optional[EvidenceRecord] = None
        if getattr(run, "evidence_id", None) is not None:
            evidence = self.get_evidence_record(project_id, cast(int, run.evidence_id))

        inspection_result = (
            self.db.query(InspectionResult)
            .filter(InspectionResult.inspection_run_id == cast(int, run.id))
            .order_by(InspectionResult.created_at.desc())
            .first()
        )

        overlays = self.list_overlays_for_inspection_run(cast(int, run.id))
        findings = self.list_findings_for_inspection_run(
            cast(int, run.id),
            overlays=overlays,
        )

        return {
            "run": run,
            "project": project,
            "master_drawing": master_drawing,
            "evidence": evidence,
            "inspection_result": inspection_result,
            "overlays": overlays,
            "findings": findings,
        }

    # ------------------------------------------------------------------
    # Inspection Results + Overlays
    # ------------------------------------------------------------------

    def create_inspection_result(
        self,
        run_id: int,
        outcome: str,
        notes: Optional[str] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> InspectionResult:
        result = InspectionResult(
            inspection_run_id=run_id,
            outcome=outcome,
            notes=notes,
        )
        self.db.add(result)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(result)
        return result

    def create_drawing_overlay(
        self,
        master_drawing_id: int,
        geometry: Dict[str, Any],
        status: str,
        meta: Optional[Dict[str, Any]] = None,
        *,
        inspection_run_id: Optional[int] = None,
        diff_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> DrawingOverlay:
        """Create overlay. Exactly one of inspection_run_id or diff_id must be set (DB constraint)."""
        if (inspection_run_id is None) == (diff_id is None):
            raise ValueError("Exactly one of inspection_run_id or diff_id must be set")
        overlay = DrawingOverlay(
            master_drawing_id=master_drawing_id,
            inspection_run_id=inspection_run_id,
            diff_id=diff_id,
            geometry=geometry,
            status=status,
            meta=meta,
        )
        self.db.add(overlay)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(overlay)
        return overlay

    def list_drawing_overlays(
        self,
        master_drawing_id: int,
        *,
        inspection_run_id: Optional[int] = None,
        diff_id: Optional[int] = None,
    ) -> List[DrawingOverlay]:
        q = (
            self.db.query(DrawingOverlay)
            .filter(DrawingOverlay.master_drawing_id == master_drawing_id)
        )
        if inspection_run_id is not None:
            q = q.filter(DrawingOverlay.inspection_run_id == inspection_run_id)
        if diff_id is not None:
            q = q.filter(DrawingOverlay.diff_id == diff_id)
        return (
            q.order_by(DrawingOverlay.created_at.desc(), DrawingOverlay.id.desc())
            .all()
        )

    def list_overlays_for_inspection_run(
        self,
        inspection_run_id: int,
    ) -> List[DrawingOverlay]:
        """List overlays originating from a specific inspection run."""
        return (
            self.db.query(DrawingOverlay)
            .filter(DrawingOverlay.inspection_run_id == inspection_run_id)
            .order_by(DrawingOverlay.created_at.desc(), DrawingOverlay.id.desc())
            .all()
        )

    def list_findings_for_inspection_run(
        self,
        inspection_run_id: int,
        *,
        overlays: Optional[Sequence[DrawingOverlay]] = None,
    ) -> List[Finding]:
        """
        Return Findings associated with an inspection run.

        Looks for finding_id stored in overlay meta or linked via drawing diffs.
        Optionally accept pre-fetched overlays to avoid duplicate queries.
        """
        overlay_records = list(overlays) if overlays is not None else self.list_overlays_for_inspection_run(inspection_run_id)
        finding_ids: Set[int] = set()

        diff_ids: Set[int] = set()
        for overlay in overlay_records:
            diff_id = getattr(overlay, "diff_id", None)
            if isinstance(diff_id, int):
                diff_ids.add(diff_id)

            meta = getattr(overlay, "meta", None)
            if isinstance(meta, dict):
                candidate = meta.get("finding_id")
                if isinstance(candidate, int):
                    finding_ids.add(candidate)
                elif candidate is not None:
                    try:
                        candidate_int = int(candidate)
                    except (TypeError, ValueError):
                        candidate_int = None
                    if candidate_int is not None:
                        finding_ids.add(candidate_int)

        if diff_ids:
            diff_rows = (
                self.db.query(DrawingDiff.id, DrawingDiff.finding_id)
                .filter(DrawingDiff.id.in_(diff_ids))
                .all()
            )
            for diff_id, linked_finding_id in diff_rows:
                if linked_finding_id is not None:
                    finding_ids.add(int(linked_finding_id))

        if not finding_ids:
            return []

        return (
            self.db.query(Finding)
            .filter(Finding.id.in_(finding_ids))
            .order_by(Finding.created_at.desc(), Finding.id.desc())
            .all()
        )

    def get_submittals(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def get_submittal(self, submittal_id: str) -> Optional[Dict[str, Any]]:
        return None

    def create_submittal(self, submittal_data: dict) -> Dict[str, Any]:
        return dict(submittal_data)

    def update_submittal(self, submittal_id: str, updates: dict) -> Optional[Dict[str, Any]]:
        return None

    def get_rfis(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def get_rfi(self, rfi_id: str) -> Optional[Dict[str, Any]]:
        return None

    def create_rfi(self, rfi_data: dict) -> Dict[str, Any]:
        return dict(rfi_data)

    def update_rfi(self, rfi_id: str, updates: dict) -> Optional[Dict[str, Any]]:
        return None

    def get_inspections(
        self,
        project_id: Optional[str] = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """List inspections with pagination. Returns (items, total). Placeholder: always empty."""
        return [], 0

    def get_inspection(self, inspection_id: str) -> Optional[Dict[str, Any]]:
        return None

    def create_inspection(self, inspection_data: dict) -> Dict[str, Any]:
        return dict(inspection_data)

    def update_inspection(self, inspection_id: str, updates: dict) -> Optional[Dict[str, Any]]:
        return None

    def get_objects(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def get_object(self, object_id: str) -> Optional[Dict[str, Any]]:
        return None

    def get_insights(
        self,
        project_id: Optional[int] = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Finding], int]:
        """List AI findings/insights with pagination. Returns (items, total)."""
        q = self.db.query(Finding)
        if project_id is not None:
            q = q.filter(Finding.project_id == project_id)
        base = q.order_by(Finding.created_at.desc(), Finding.id.desc())
        total = base.count()
        items = base.limit(limit).offset(offset).all()
        return items, total

    def get_project_findings(
        self,
        project_id: int,
        limit: Optional[int] = None,
    ) -> List[Finding]:
        """List findings for a project (dashboard). Use get_insights for paginated insights page."""
        q = self.db.query(Finding).filter(Finding.project_id == project_id)
        q = q.order_by(Finding.created_at.desc(), Finding.id.desc())
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def count_project_findings(self, project_id: int) -> int:
        """Count findings for a project (for pagination metadata)."""
        return self.db.query(Finding).filter(Finding.project_id == project_id).count()

    def get_finding(
        self,
        finding_id: int,
        project_id: Optional[int] = None,
    ) -> Optional[Finding]:
        q = self.db.query(Finding).filter(Finding.id == finding_id)
        if project_id is not None:
            q = q.filter(Finding.project_id == project_id)
        return q.first()

    def resolve_insight(self, insight_id: int) -> Optional[Finding]:
        finding = self.db.query(Finding).filter(Finding.id == insight_id).first()
        if finding is None:
            return None

        setattr(finding, "resolved", True)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(finding)
        return finding

    def create_usage_log(
        self,
        user_id: int,
        action: str,
        *,
        company_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        processing_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageLog:
        """Create a UsageLog entry for telemetry/monitoring. Optionally called after diff runs."""
        log = UsageLog(
            user_id=user_id,
            company_id=company_id,
            action=action,
            resource_type=resource_type,
            processing_time=processing_time,
            log_metadata=metadata,
        )
        self.db.add(log)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(log)
        return log

    def create_procore_writeback(
        self,
        *,
        project_id: int,
        writeback_type: str,
        mode: str,
        idempotency_key: str,
        inspection_run_id: Optional[int] = None,
        finding_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ProcoreWriteback:
        row = ProcoreWriteback(
            project_id=project_id,
            inspection_run_id=inspection_run_id,
            finding_id=finding_id,
            writeback_type=writeback_type,
            mode=mode,
            status="in_progress",
            payload=payload,
            idempotency_key=idempotency_key,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_procore_writeback(
        self,
        writeback_id: int,
        *,
        status: str,
        procore_response: Optional[Dict[str, Any]] = None,
        resource_reference: Optional[Dict[str, Any]] = None,
    ) -> Optional[ProcoreWriteback]:
        row = self.db.query(ProcoreWriteback).filter(ProcoreWriteback.id == writeback_id).first()
        if row is None:
            return None
        row.status = status  # type: ignore[assignment]
        if procore_response is not None:
            row.procore_response = procore_response  # type: ignore[assignment]
        if resource_reference is not None:
            row.resource_reference = resource_reference  # type: ignore[assignment]
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_dashboard_stats(self) -> Dict[str, Any]:
        return {
            "total_projects": 0,
            "active_projects": 0,
            "total_submittals": 0,
            "pending_review": 0,
            "approved_today": 0,
            "open_rfis": 0,
            "overdue_rfis": 0,
            "scheduled_inspections": 0,
            "pass_rate": 100,
            "ai_insights_count": 0,
            "critical_alerts": 0,
        }
