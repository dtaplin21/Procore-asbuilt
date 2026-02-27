from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db
from models.database import Project  # <-- IMPORTANT: your repo uses models.database

router = APIRouter(prefix="/api/projects", tags=["project-dashboard"])


@router.get("/{project_id}/dashboard/summary")
def get_project_dashboard_summary(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Extension-style summary: "anchor" + "health", not Procore business KPIs
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "status": getattr(project, "status", "active"),
            "company_id": project.company_id,
            "procore_project_id": project.procore_project_id,
        },
        "integration": {
            "last_sync_at": project.last_sync_at.isoformat() if getattr(project, "last_sync_at", None) else None,
            "sync_status": getattr(project, "sync_status", "idle"),
            "sync_error": None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }