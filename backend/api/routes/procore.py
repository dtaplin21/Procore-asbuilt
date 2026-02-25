from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from services.procore_client import ProcoreAPIClient
from typing import Optional
from errors import ProcoreNotConnected
from services.procore_connection_store import get_active_connection

router = APIRouter(prefix="/api/procore", tags=["procore"])

@router.post("/sync")
async def sync_procore(
    user_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Sync data from Procore"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        # Sync projects if no specific project_id
        if not project_id:
            projects = await client.get_projects()
            # TODO: Store projects in local database
            return {"synced": len(projects), "message": f"Synced {len(projects)} projects"}
        else:
            # Sync specific project data
            # TODO: Sync submittals, RFIs, inspections, etc.
            return {"synced": True, "project_id": project_id}

