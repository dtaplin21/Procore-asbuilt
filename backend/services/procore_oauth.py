"""
Procore OAuth 2.0 Handler
Manages OAuth flow, token exchange/refresh, and DB persistence via procore_connections
"""
import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from config import settings
from typing import Dict, Any, Optional
import secrets
from errors import ExternalServiceError, ProcoreAuthExpired, ProcoreNotConnected, ProcoreOAuthError

from models.models import Company
from services.procore_connection_store import get_active_connection, upsert_connection

class ProcoreOAuth:
    """Handles Procore OAuth 2.0 authentication flow"""
    
    AUTHORIZATION_URL = "https://login.procore.com/oauth/authorize"
    TOKEN_URL = "https://login.procore.com/oauth/token"
    
    def __init__(self, db: Session):
        self.db = db
        self.client_id = settings.procore_client_id
        self.client_secret = settings.procore_client_secret
        self.redirect_uri = settings.procore_redirect_uri
    
    def generate_state(self) -> str:
        """Generate secure state parameter for OAuth flow"""
        return secrets.token_urlsafe(32)
    
    def get_authorization_url(self, state: str) -> str:
        """Generate Procore OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
            # keep this scope string here (Procore expects space-delimited scopes)
            "scope": "read write",
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTHORIZATION_URL}?{query_string}"
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access + refresh token payload.

        IMPORTANT: This does not store tokens. The OAuth callback persists after /me and /companies.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": self.redirect_uri,
                        "grant_type": "authorization_code",
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                response.raise_for_status()
                token_data = response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            details = {"upstream": "procore_oauth", "upstream_status": status}
            # Invalid code/redirect mismatch etc typically surface as 400
            if status in (400, 401, 403):
                raise ProcoreOAuthError(details=details) from e
            raise ExternalServiceError(message="Procore OAuth token exchange failed", details=details) from e
        except httpx.RequestError as e:
            raise ExternalServiceError(message="Failed to reach Procore OAuth", details={"upstream": "procore_oauth"}) from e
        
        # Calculate expiration time
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": expires_at,
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope"),
        }
    
    async def refresh_token(self, procore_user_id: str) -> Dict[str, Any]:
        """
        Refresh the ACTIVE connection for this procore_user_id and persist updates to DB.
        """
        conn = get_active_connection(self.db, procore_user_id)
        if not conn:
            raise ProcoreNotConnected(details={"user_id": procore_user_id})

        current_refresh = conn.refresh_token

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": current_refresh,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                response.raise_for_status()
                token_data = response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            details = {"upstream": "procore_oauth", "upstream_status": status}
            if status in (401, 403):
                raise ProcoreAuthExpired(details=details) from e
            if status == 400:
                raise ProcoreOAuthError(message="Procore refresh token invalid", details=details) from e
            raise ExternalServiceError(message="Procore token refresh failed", details=details) from e
        except httpx.RequestError as e:
            raise ExternalServiceError(message="Failed to reach Procore OAuth", details={"upstream": "procore_oauth"}) from e
        
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        new_payload = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", current_refresh),
            "expires_at": expires_at,
            "token_type": token_data.get("token_type", conn.token_type or "Bearer"),
            "scope": token_data.get("scope", conn.scope),
        }

        # Persist refresh results into the SAME (company_id, procore_user_id) row
        upsert_connection(
            db=self.db,
            company_id=conn.company_id,
            procore_user_id=str(procore_user_id),
            access_token=new_payload["access_token"],
            refresh_token=new_payload["refresh_token"],
            token_expires_at=new_payload["expires_at"],
            token_type=new_payload["token_type"],
            scope=new_payload["scope"],
            make_active=True,
        )

        return new_payload
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get current user info from Procore"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.procore.com/rest/v1.0/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            
            response.raise_for_status()
            return response.json()
    
    async def sync_user_info(self, token_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calls /me + /companies (and best-effort /projects for first company),
        then persists token payload to procore_connections (Approach B).
        """
        access_token = token_payload["access_token"]
        user_info = await self.get_user_info(access_token)
        procore_user_id = str(user_info["id"])
        
        # Get companies user belongs to
        async with httpx.AsyncClient(timeout=30.0) as client:
            companies_response = await client.get(
                "https://api.procore.com/rest/v1.0/companies",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            companies_response.raise_for_status()
            companies = companies_response.json()

            company_ids = [str(c["id"]) for c in companies]

            project_ids = []
            if companies:
                first_procore_company_id = str(companies[0]["id"])
                projects_response = await client.get(
                    "https://api.procore.com/rest/v1.0/projects",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Procore-Company-Id": first_procore_company_id,
                        "Content-Type": "application/json",
                    },
                )
                if projects_response.status_code == 200:
                    projects = projects_response.json()
                    project_ids = [str(p["id"]) for p in projects]

        # Upsert Company rows (keyed by Company.procore_company_id)
        internal_company_id: Optional[int] = None
        for c in companies:
            procore_company_id = str(c["id"])
            name = c.get("name") or f"Procore Company {procore_company_id}"

            row = (
                self.db.query(Company)
                .filter(Company.procore_company_id == procore_company_id)
                .first()
            )
            if not row:
                row = Company(name=name, procore_company_id=procore_company_id)
                self.db.add(row)
                self.db.flush()

            if internal_company_id is None:
                internal_company_id = row.id

        if internal_company_id is None:
            raise ProcoreOAuthError(message="No Procore companies found")

        # Persist token payload for default (first) company and set active context
        upsert_connection(
            db=self.db,
            company_id=internal_company_id,
            procore_user_id=procore_user_id,
            access_token=token_payload["access_token"],
            refresh_token=token_payload["refresh_token"],
            token_expires_at=token_payload["expires_at"],
            token_type=token_payload.get("token_type", "Bearer"),
            scope=token_payload.get("scope"),
            make_active=True,
        )

        return {
            "procore_user_id": procore_user_id,
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "company_ids": company_ids,
            "project_ids": project_ids,
            "last_synced_at": datetime.utcnow().isoformat(),
        }

