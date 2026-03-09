"""
Storage service.

This project previously had table-backed demo endpoints (projects/submittals/rfis/etc).
Those ORM models and schemas have been removed. We keep this service as a placeholder
so routes can continue to import it while the new data model is designed.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List, Optional, Sequence, Set, cast

from models.models import (
    Project,
    Finding,
    Drawing,
    DrawingRegion,
    DrawingAlignment,
    DrawingDiff,
    EvidenceRecord,
    UsageLog,
    InspectionRun,
    InspectionResult,
    DrawingOverlay,
)
from services.procore_connection_store import get_active_connection


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
        }
    
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

    def get_drawing(self, project_id: int, drawing_id: int) -> Optional[Drawing]:
        return (
            self.db.query(Drawing)
            .filter(Drawing.project_id == project_id, Drawing.id == drawing_id)
            .first()
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
        "type": "homography",
        "matrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "confidence": 1.0,
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
        # MVP: manual alignments complete immediately with identity transform
        if method.strip().lower() == "manual":
            status = "complete"
            transform = self.IDENTITY_TRANSFORM
        else:
            status = "queued"
            transform = None

        alignment = DrawingAlignment(
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
            )
            .first()
        )
        if alignment is None:
            return None
        if self.get_drawing(project_id, master_drawing_id) is None:
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

        finding = Finding(
            project_id=project_id,
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
    ) -> Finding:
        """Create a Finding (used by inspection pipeline, etc.)."""
        finding = Finding(
            project_id=project_id,
            type=type,
            severity=severity,
            title=title,
            description=description,
            affected_items=affected_items or [],
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

    # ------------------------------------------------------------------
    # Inspection Runs
    # ------------------------------------------------------------------

    def create_inspection_run(
        self,
        project_id: int,
        master_drawing_id: int,
        evidence_id: Optional[int] = None,
        inspection_type: Optional[str] = None,
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
