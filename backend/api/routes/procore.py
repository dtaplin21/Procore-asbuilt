from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models.schemas import ProcoreConnection
from datetime import datetime

router = APIRouter(prefix="/api/procore", tags=["procore"])

@router.get("/status", response_model=ProcoreConnection)
async def get_procore_status(db: Session = Depends(get_db)):
    # TODO: Implement actual Procore connection status check
    # For now, return mock data
    return ProcoreConnection(
        connected=True,
        last_synced_at=datetime.utcnow(),
        sync_status="idle",
        projects_linked=3
    )

@router.get("/oauth/authorize")
async def authorize_procore():
    # TODO: Implement Procore OAuth authorization flow
    # Redirect to Procore OAuth URL
    pass

@router.get("/oauth/callback")
async def procore_oauth_callback(code: str, state: str):
    # TODO: Handle OAuth callback and exchange code for tokens
    pass

@router.post("/sync")
async def sync_procore(db: Session = Depends(get_db)):
    # TODO: Implement Procore data sync
    pass

