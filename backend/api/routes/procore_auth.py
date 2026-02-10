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
from models.schemas import ProcoreConnection
from datetime import datetime
from typing import Optional
import secrets

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
    db: Session = Depends(get_db)
):
    """Handle OAuth callback from Procore"""
    oauth = ProcoreOAuth(db)
    
    # Verify state
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    # Exchange code for tokens
    try:
        # Generate temporary user_id (in production, get from session)
        temp_user_id = secrets.token_urlsafe(16)
        
        token = await oauth.exchange_code_for_tokens(code, temp_user_id)
        
        # Get user info and sync
        user = await oauth.sync_user_info(temp_user_id, token.access_token)
        
        # Update token with actual user_id
        token.user_id = user.procore_user_id
        db.commit()
        
        # Clean up state
        del _oauth_states[state]
        
        # Redirect to frontend with success
        return RedirectResponse(
            url=f"http://localhost:5173/settings?procore_connected=true&user_id={user.procore_user_id}"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete OAuth flow: {str(e)}")

@router.post("/oauth/refresh")
async def refresh_procore_token(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Refresh Procore access token"""
    oauth = ProcoreOAuth(db)
    
    token = oauth.get_token(user_id)
    if not token:
        raise HTTPException(status_code=404, detail="No token found for user")
    
    try:
        new_token = await oauth.refresh_token(token.refresh_token, user_id)
        return {
            "success": True,
            "expires_at": new_token.expires_at.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh token: {str(e)}")

@router.get("/status")
async def get_procore_status(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get Procore connection status for user"""
    oauth = ProcoreOAuth(db)
    
    token = oauth.get_token(user_id)
    
    if not token:
        return ProcoreConnection(
            connected=False,
            sync_status="idle",
            projects_linked=0,
            error_message="Not connected to Procore"
        )
    
    # Check if token is expired
    is_expired = datetime.utcnow() >= token.expires_at
    
    if is_expired:
        try:
            # Attempt to refresh
            token = await oauth.refresh_token(token.refresh_token, user_id)
        except Exception as e:
            return ProcoreConnection(
                connected=False,
                sync_status="error",
                projects_linked=0,
                error_message=f"Token expired and refresh failed: {str(e)}"
            )
    
    # Get user info to count projects
    from models.database import ProcoreUser
    user = db.query(ProcoreUser).filter(
        ProcoreUser.procore_user_id == user_id
    ).first()
    
    projects_linked = len(user.project_ids) if user else 0
    
    return ProcoreConnection(
        connected=True,
        last_synced_at=user.last_synced_at.isoformat() if user and user.last_synced_at else None,
        sync_status="idle",
        projects_linked=projects_linked
    )

@router.get("/me")
async def get_current_user(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get current authenticated user info"""
    oauth = ProcoreOAuth(db)
    token = oauth.get_token(user_id)
    
    if not token:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            user_info = await client.get_current_user()
            return user_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user info: {str(e)}")

@router.get("/companies")
async def get_companies(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """List all companies user has access to"""
    oauth = ProcoreOAuth(db)
    token = oauth.get_token(user_id)
    
    if not token:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            companies = await client.get_companies()
            return companies
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get companies: {str(e)}")

@router.get("/projects")
async def get_projects(
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all projects user has access to"""
    oauth = ProcoreOAuth(db)
    token = oauth.get_token(user_id)
    
    if not token:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            projects = await client.get_projects(company_id)
            return projects
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get projects: {str(e)}")

@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get project details"""
    oauth = ProcoreOAuth(db)
    token = oauth.get_token(user_id)
    
    if not token:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            project = await client.get_project(project_id, company_id)
            return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project: {str(e)}")

@router.get("/projects/{project_id}/team")
async def get_project_team(
    project_id: str,
    user_id: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get project team members"""
    oauth = ProcoreOAuth(db)
    token = oauth.get_token(user_id)
    
    if not token:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            team = await client.get_project_users(project_id, company_id)
            return team
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project team: {str(e)}")

@router.post("/disconnect")
async def disconnect_procore(
    user_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Disconnect Procore account"""
    oauth = ProcoreOAuth(db)
    
    success = oauth.delete_token(user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="No Procore connection found")
    
    return {"success": True, "message": "Disconnected from Procore"}

