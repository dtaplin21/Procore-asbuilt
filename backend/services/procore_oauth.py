"""
Procore OAuth 2.0 Handler
Manages OAuth flow, token storage, and refresh
"""
import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from config import settings
from typing import Optional, Dict, Any
import secrets
import hashlib
from errors import ExternalServiceError, ProcoreAuthExpired, ProcoreNotConnected, ProcoreOAuthError
from services.procore_token_store import ProcoreTokenRecord, delete_token, get_token, move_token, upsert_token

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
            "scope": "read write"  # Adjust based on Procore's scope requirements
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTHORIZATION_URL}?{query_string}"
    
    async def exchange_code_for_tokens(
        self,
        code: str,
        user_id: Optional[str] = None
    ) -> ProcoreTokenRecord:
        """Exchange authorization code for access and refresh tokens"""
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
        
        # Extract user info from token response or make separate API call
        # For now, we'll need to get user_id from a separate call after getting token
        
        # Calculate expiration time
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        if not user_id:
            # We need a key to store the token. Routes pass a temp id and later re-key it
            # to the real Procore user id once /me is fetched.
            raise ProcoreOAuthError(message="Missing user_id for token storage")

        record = ProcoreTokenRecord(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=expires_at,
            token_type=token_data.get("token_type", "Bearer"),
            scope=token_data.get("scope"),
        )
        return upsert_token(user_id, record)
    
    async def refresh_token(
        self,
        refresh_token: str,
        user_id: str
    ) -> ProcoreTokenRecord:
        """Refresh access token using refresh token"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
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

        token = get_token(user_id)
        if not token:
            raise ProcoreNotConnected(details={"user_id": user_id})

        token.access_token = token_data["access_token"]
        token.refresh_token = token_data.get("refresh_token", refresh_token)  # May get new refresh token
        token.expires_at = expires_at
        token.token_type = token_data.get("token_type", token.token_type)
        token.scope = token_data.get("scope", token.scope)

        return upsert_token(user_id, token)
    
    def get_token(self, user_id: str) -> Optional[ProcoreTokenRecord]:
        """Get stored token for user"""
        return get_token(user_id)
    
    def delete_token(self, user_id: str) -> bool:
        """Delete token for user (disconnect)"""
        return delete_token(user_id)
    
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
    
    async def sync_user_info(
        self,
        user_id: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Fetch user info from Procore.

        Note: ORM persistence has been removed; we return a plain dict and allow the
        caller (OAuth callback) to re-key the token from a temp id to the real Procore user id.
        """
        user_info = await self.get_user_info(access_token)
        
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
                company_id = str(companies[0]["id"])
                projects_response = await client.get(
                    "https://api.procore.com/rest/v1.0/projects",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Procore-Company-Id": company_id,
                        "Content-Type": "application/json",
                    },
                )
                if projects_response.status_code == 200:
                    projects = projects_response.json()
                    project_ids = [str(p["id"]) for p in projects]

        # Best-effort: attach company_id onto the stored token (still keyed by caller's user_id for now)
        token = get_token(user_id)
        if token and company_ids and not token.company_id:
            token.company_id = company_ids[0]
            upsert_token(user_id, token)

        return {
            "procore_user_id": str(user_info["id"]),
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "company_ids": company_ids,
            "project_ids": project_ids,
            "last_synced_at": datetime.utcnow().isoformat(),
        }

