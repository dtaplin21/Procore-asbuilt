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

from models.models import Project, Finding


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

