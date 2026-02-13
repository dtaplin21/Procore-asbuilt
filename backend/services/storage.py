"""
Storage service.

This project previously had table-backed demo endpoints (projects/submittals/rfis/etc).
Those ORM models and schemas have been removed. We keep this service as a placeholder
so routes can continue to import it while the new data model is designed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional


class StorageService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Placeholder methods (return empty data until new models are defined)
    # ------------------------------------------------------------------

    def get_projects(self) -> List[Dict[str, Any]]:
        return []

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return None

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

    def get_insights(self, project_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return []

    def resolve_insight(self, insight_id: str) -> Optional[Dict[str, Any]]:
        return None

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

