"""
Procore Authentication Routes
Handles OAuth flow and user authentication
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from services.idempotency import (
    begin_idempotent_operation,
    finish_idempotent_operation,
    fail_idempotent_operation,
)
from services.procore_oauth import ProcoreOAuth
from services.procore_client import ProcoreAPIClient
from datetime import datetime
from typing import Optional, cast
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
    active_company_id = cast(int, active_conn.company_id) if active_conn else None

    # Redirect to frontend
    base = "http://localhost:5173/settings"
    qs = f"?procore_connected=true&user_id={procore_user_id}"
    if active_company_id is not None:
        qs += f"&company_id={active_company_id}"

    return RedirectResponse(url=f"{base}{qs}")

@router.post("/oauth/refresh")
async def refresh_procore_token(
    user_id: str = Query(...),
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
):
    """Refresh Procore access token for the user's ACTIVE company connection (DB-backed)."""
    scope = f"procore_auth:refresh:{user_id}"
    request_payload = {"user_id": user_id}

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed":
            return cached_resp
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Refresh already in progress")
        if row_status == "failed":
            return cached_resp

    try:
        oauth = ProcoreOAuth(db)
        new_payload = await oauth.refresh_token(user_id)
        response = {
            "success": True,
            "expires_at": new_payload["expires_at"].isoformat(),
        }
        finish_idempotent_operation(db, row_id=int(idem_row.id), response_payload=response)
        return response
    except Exception as e:
        fail_idempotent_operation(
            db,
            row_id=int(idem_row.id),
            response_payload={"success": False, "error": str(e)},
        )
        raise

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
            "procore_user_id": None,
            "active_company_id": None,
            "company_name": None,
        }

    # Check expiry using token_expires_at
    expires_at = cast(datetime, conn.token_expires_at)
    is_expired = datetime.utcnow() >= expires_at

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
                "procore_user_id": cast(str, conn.procore_user_id) if conn else None,
                "active_company_id": cast(int, conn.company_id) if conn else None,
                "company_name": None,
            }

    company = None
    if conn:
        company_id_val = cast(int, conn.company_id)
        company = db.query(Company).filter(Company.id == company_id_val).first()

    updated_at_val = cast(datetime, conn.updated_at) if conn else None
    return {
        "connected": True,
        "last_synced_at": updated_at_val.isoformat() if updated_at_val else None,
        "sync_status": "idle",
        "projects_linked": 0,
        "error_message": None,
        "procore_user_id": cast(str, conn.procore_user_id) if conn else None,
        "active_company_id": cast(int, conn.company_id) if conn else None,
        "company_name": cast(str, company.name) if company else None,
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
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
):
    """
    Switch active Procore company context for this procore_user_id.
    Marks other connections inactive and activates this one.
    """
    scope = f"procore_auth:company_select:{user_id}:{company_id}"
    request_payload = {"user_id": user_id, "company_id": company_id}

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed":
            return cached_resp
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Company select already in progress")
        if row_status == "failed":
            return cached_resp

    conn = get_connection(db, company_id, user_id)
    if not conn:
        fail_idempotent_operation(
            db,
            row_id=int(idem_row.id),
            response_payload={"success": False, "error": "No Procore connection found for that company/user"},
        )
        raise HTTPException(status_code=404, detail="No Procore connection found for that company/user")

    set_active_company(db, user_id, company_id)
    db.commit()

    response = {"success": True, "active_company_id": int(company_id)}
    finish_idempotent_operation(db, row_id=int(idem_row.id), response_payload=response)
    return response

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
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
):
    """
    Disconnect Procore.

    If company_id is provided: delete that specific (company_id, user_id) connection.
    If not provided: delete the ACTIVE connection.
    """
    scope_suffix = company_id if company_id is not None else "active"
    scope = f"procore_auth:disconnect:{user_id}:{scope_suffix}"
    request_payload = {"user_id": user_id, "company_id": company_id}

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed":
            return cached_resp
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Disconnect already in progress")
        if row_status == "failed":
            return cached_resp

    if company_id is None:
        active = get_active_connection(db, user_id)
        if not active:
            fail_idempotent_operation(
                db,
                row_id=int(idem_row.id),
                response_payload={"success": False, "error": "No Procore connection found"},
            )
            raise HTTPException(status_code=404, detail="No Procore connection found")
        company_id = cast(int, active.company_id)

    delete_connection(db, user_id, company_id)

    response = {"success": True, "message": "Disconnected from Procore"}
    finish_idempotent_operation(db, row_id=int(idem_row.id), response_payload=response)
    return response

