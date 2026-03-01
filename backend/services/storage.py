"""
Storage service.

This project previously had table-backed demo endpoints (projects/submittals/rfis/etc).
Those ORM models and schemas have been removed. We keep this service as a placeholder
so routes can continue to import it while the new data model is designed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List, Optional

from models.models import Project, Finding, Drawing, EvidenceRecord
from services.procore_connection_store import get_active_connection


class StorageService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Placeholder methods (return empty data until new models are defined)
    # ------------------------------------------------------------------

    def get_projects(self, company_id: Optional[int] = None) -> List[Project]:
        q = self.db.query(Project)
        if company_id is not None:
            q = q.filter(Project.company_id == company_id)
        return q.order_by(Project.name.asc()).all()

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
        project_company_id = int(project.company_id)
        matches_active_company = bool(active_company_id == project_company_id) if active_company_id is not None else False

        # NOTE: Return datetimes as datetime objects. If the route uses a Pydantic response_model
        # (recommended), FastAPI will serialize these. If returning raw dict without a model,
        # you may want to .isoformat() them instead.
        return {
            "project": {
                "id": int(project.id),
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
    ) -> List[EvidenceRecord]:
        q = self.db.query(EvidenceRecord).filter(EvidenceRecord.project_id == project_id)
        if type is not None:
            q = q.filter(EvidenceRecord.type == type)
        return q.order_by(EvidenceRecord.created_at.desc(), EvidenceRecord.id.desc()).all()

    def get_evidence_record(self, project_id: int, evidence_id: int) -> Optional[EvidenceRecord]:
        return (
            self.db.query(EvidenceRecord)
            .filter(EvidenceRecord.project_id == project_id, EvidenceRecord.id == evidence_id)
            .first()
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

    def get_inspections(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

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

    def get_insights(self, project_id: Optional[int] = None, limit: Optional[int] = None) -> List[Finding]:
        q = self.db.query(Finding)
        if project_id is not None:
            q = q.filter(Finding.project_id == project_id)
        q = q.order_by(Finding.created_at.desc(), Finding.id.desc())
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def resolve_insight(self, insight_id: int) -> Optional[Finding]:
        finding = self.db.query(Finding).filter(Finding.id == insight_id).first()
        if finding is None:
            return None

        finding.resolved = True
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        self.db.refresh(finding)
        return finding

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

