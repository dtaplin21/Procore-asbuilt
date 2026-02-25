"""
Procore Authentication Routes
Handles OAuth flow and user authentication
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from services.procore_oauth import ProcoreOAuth
from services.procore_client import ProcoreAPIClient
from datetime import datetime
from typing import Optional
import secrets
from errors import ProcoreNotConnected
from models.models import Company
from services.procore_connection_store import (
    get_active_connection,
    get_connection,
    set_active_company,
    upsert_connection,
    delete_connection,
)

router = APIRouter(prefix="/api/procore", tags=["procore-auth"])

# Store state temporarily (in production, use Redis or database)
_oauth_states = {}

@router.get("/oauth/authorize")
async def authorize_procore(
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate Procore OAuth authorization flow"""
    oauth = ProcoreOAuth(db)
    
    # Generate secure state
    state = oauth.generate_state()
    
    # Store state temporarily (in production, store in session/Redis)
    _oauth_states[state] = {
        "created_at": datetime.utcnow(),
        "user_session": None  # Could store user session ID here
    }
    
    # Generate authorization URL
    auth_url = oauth.get_authorization_url(state)
    
    # Redirect to Procore
    return RedirectResponse(url=auth_url)

@router.get("/oauth/callback")
async def procore_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Handle OAuth callback from Procore (DB persistence, no temp IDs)"""
    oauth = ProcoreOAuth(db)

    # Verify state
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    # Exchange code -> token payload (does NOT store)
    token_payload = await oauth.exchange_code_for_tokens(code)

    # /me + /companies + persist default company connection
    user = await oauth.sync_user_info(token_payload)

    procore_user_id = str(user.get("procore_user_id", ""))

    # Clean up state
    del _oauth_states[state]

    # Determine the internal company_id we activated (first company persisted in sync_user_info)
    active_conn = get_active_connection(db, procore_user_id)
    active_company_id = active_conn.company_id if active_conn else None

    # Redirect to frontend
    base = "http://localhost:5173/settings"
    qs = f"?procore_connected=true&user_id={procore_user_id}"
    if active_company_id:
        qs += f"&company_id={active_company_id}"

    return RedirectResponse(url=f"{base}{qs}")

@router.post("/oauth/refresh")
async def refresh_procore_token(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """Refresh Procore access token for the user's ACTIVE company connection (DB-backed)."""
    oauth = ProcoreOAuth(db)

    # This refresh loads active connection from DB and persists updated tokens
    new_payload = await oauth.refresh_token(user_id)

    return {
        "success": True,
        "expires_at": new_payload["expires_at"].isoformat(),
    }

@router.get("/status")
async def get_procore_status(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """Get Procore connection status for user (DB-backed)."""
    oauth = ProcoreOAuth(db)

    conn = get_active_connection(db, user_id)
    if not conn:
        return {
            "connected": False,
            "last_synced_at": None,
            "sync_status": "idle",
            "projects_linked": 0,
            "error_message": "Not connected to Procore",
        }

    # Check expiry using token_expires_at
    is_expired = datetime.utcnow() >= conn.token_expires_at

    if is_expired:
        try:
            await oauth.refresh_token(user_id)  # refreshes + persists active row
            conn = get_active_connection(db, user_id)
        except Exception as e:
            return {
                "connected": False,
                "last_synced_at": None,
                "sync_status": "error",
                "projects_linked": 0,
                "error_message": f"Token expired and refresh failed: {str(e)}",
            }

    return {
        "connected": True,
        "last_synced_at": conn.updated_at.isoformat() if conn and conn.updated_at else None,
        "sync_status": "idle",
        "projects_linked": 0,
        "error_message": None,
        "active_company_id": conn.company_id if conn else None,
    }

@router.get("/me")
async def get_current_user(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get current authenticated user info"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        user_info = await client.get_current_user()
        return user_info

@router.get("/companies")
async def get_companies(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """List all companies user has access to"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        companies = await client.get_companies()
        return companies


@router.get("/companies/local")
async def get_local_companies(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Returns local Company rows (internal id) for the companies the user has access to.
    Uses ProcoreAPIClient to fetch /companies, then maps to DB Company records.
    """
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})

    async with ProcoreAPIClient(db, user_id) as client:
        procore_companies = await client.get_companies()

    procore_ids = [str(c.get("id")) for c in (procore_companies or []) if c.get("id") is not None]
    if not procore_ids:
        return []

    rows = db.query(Company).filter(Company.procore_company_id.in_(procore_ids)).all()

    return [
        {"id": r.id, "name": r.name, "procore_company_id": r.procore_company_id}
        for r in rows
    ]

@router.post("/company/select")
async def select_active_company(
    user_id: str = Query(...),
    company_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Switch active Procore company context for this procore_user_id.
    Marks other connections inactive and activates this one.
    """
    # Require that a connection row exists for this (company_id, user_id)
    conn = get_connection(db, company_id, user_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No Procore connection found for that company/user")

    set_active_company(db, user_id, company_id)
    db.commit()

    return {"success": True, "active_company_id": int(company_id)}

@router.get("/projects")
async def get_projects(
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all projects user has access to"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        projects = await client.get_projects(company_id)
        return projects

@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get project details"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        project = await client.get_project(project_id, company_id)
        return project

@router.get("/projects/{project_id}/team")
async def get_project_team(
    project_id: str,
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get project team members"""
    conn = get_active_connection(db, user_id)
    if not conn:
        raise ProcoreNotConnected(details={"user_id": user_id})
    
    async with ProcoreAPIClient(db, user_id) as client:
        team = await client.get_project_users(project_id, company_id)
        return team

@router.post("/disconnect")
async def disconnect_procore(
    user_id: str = Query(...),
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Disconnect Procore.

    If company_id is provided: delete that specific (company_id, user_id) connection.
    If not provided: delete the ACTIVE connection.
    """
    if company_id is None:
        active = get_active_connection(db, user_id)
        if not active:
            raise HTTPException(status_code=404, detail="No Procore connection found")
        company_id = active.company_id

    delete_connection(db, user_id, company_id)

    return {"success": True, "message": "Disconnected from Procore"}

