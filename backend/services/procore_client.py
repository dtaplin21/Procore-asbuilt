"""
Procore API Client Service
Handles all HTTP requests to Procore API with authentication
"""
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.database import ProcoreToken
import json

class ProcoreAPIClient:
    """Main client for interacting with Procore REST API"""
    
    BASE_URL = "https://api.procore.com"
    API_VERSION = "v1.0"
    
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    async def _get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary"""
        from services.procore_oauth import ProcoreOAuth
        
        token = self.db.query(ProcoreToken).filter(
            ProcoreToken.user_id == self.user_id
        ).first()
        
        if not token:
            raise ValueError(f"No Procore token found for user {self.user_id}")
        
        # Check if token is expired or expires soon (within 5 minutes)
        if datetime.utcnow() >= token.expires_at - timedelta(minutes=5):
            # Refresh token
            oauth = ProcoreOAuth(self.db)
            new_token = await oauth.refresh_token(token.refresh_token, self.user_id)
            return new_token.access_token
        
        return token.access_token
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Procore API"""
        access_token = await self._get_access_token()
        
        url = f"{self.BASE_URL}/rest/{self.API_VERSION}/{endpoint.lstrip('/')}"
        
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Procore-Company-Id": self._get_company_id(),  # Will be set per request
        }
        
        if headers:
            request_headers.update(headers)
        
        if not self._client:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=request_headers
                )
        else:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=request_headers
            )
        
        response.raise_for_status()
        return response.json()
    
    def _get_company_id(self) -> str:
        """Get company ID from token - will be set per request"""
        token = self.db.query(ProcoreToken).filter(
            ProcoreToken.user_id == self.user_id
        ).first()
        return token.company_id or ""
    
    # User & Company Methods
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current authenticated user info"""
        return await self._request("GET", "/me")
    
    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user details by ID"""
        return await self._request("GET", f"/users/{user_id}")
    
    async def get_companies(self) -> List[Dict[str, Any]]:
        """List all companies user has access to"""
        return await self._request("GET", "/companies")
    
    async def get_company(self, company_id: str) -> Dict[str, Any]:
        """Get company details"""
        headers = {"Procore-Company-Id": company_id}
        return await self._request("GET", f"/companies/{company_id}", headers=headers)
    
    # Project Methods
    async def get_projects(self, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all projects user has access to"""
        params = {}
        if company_id:
            params["company_id"] = company_id
        
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request("GET", "/projects", params=params, headers=headers)
    
    async def get_project(self, project_id: str, company_id: Optional[str] = None) -> Dict[str, Any]:
        """Get project details"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request("GET", f"/projects/{project_id}", headers=headers)
    
    async def get_project_users(self, project_id: str, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get project team members"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request("GET", f"/projects/{project_id}/users", headers=headers)
    
    async def get_project_companies(self, project_id: str, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get companies on project"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request("GET", f"/projects/{project_id}/companies", headers=headers)
    
    # Submittals Methods
    async def get_submittals(
        self,
        project_id: str,
        company_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List submittals for a project"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        request_params = {"project_id": project_id}
        if params:
            request_params.update(params)
        
        return await self._request("GET", "/submittals", params=request_params, headers=headers)
    
    async def get_submittal(
        self,
        submittal_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get submittal details"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "GET",
            f"/submittals/{submittal_id}",
            params={"project_id": project_id},
            headers=headers
        )
    
    async def create_submittal_response(
        self,
        submittal_id: str,
        project_id: str,
        response_data: Dict[str, Any],
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit review response to submittal"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "POST",
            f"/submittals/{submittal_id}/responses",
            params={"project_id": project_id},
            json_data=response_data,
            headers=headers
        )
    
    async def update_submittal(
        self,
        submittal_id: str,
        project_id: str,
        updates: Dict[str, Any],
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update submittal"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "PATCH",
            f"/submittals/{submittal_id}",
            params={"project_id": project_id},
            json_data=updates,
            headers=headers
        )
    
    async def get_submittal_attachments(
        self,
        submittal_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get submittal attachments"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "GET",
            f"/submittals/{submittal_id}/attachments",
            params={"project_id": project_id},
            headers=headers
        )
    
    # RFIs Methods
    async def get_rfis(
        self,
        project_id: str,
        company_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List RFIs for a project"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        request_params = {"project_id": project_id}
        if params:
            request_params.update(params)
        
        return await self._request("GET", "/rfis", params=request_params, headers=headers)
    
    async def get_rfi(
        self,
        rfi_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get RFI details"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "GET",
            f"/rfis/{rfi_id}",
            params={"project_id": project_id},
            headers=headers
        )
    
    async def create_rfi_response(
        self,
        rfi_id: str,
        project_id: str,
        response_data: Dict[str, Any],
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit response to RFI"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "POST",
            f"/rfis/{rfi_id}/responses",
            params={"project_id": project_id},
            json_data=response_data,
            headers=headers
        )
    
    # Drawings Methods
    async def get_drawings(
        self,
        project_id: str,
        company_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List drawings for a project"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        request_params = {"project_id": project_id}
        if params:
            request_params.update(params)
        
        return await self._request("GET", "/drawings", params=request_params, headers=headers)
    
    async def get_drawing(
        self,
        drawing_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get drawing details"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "GET",
            f"/drawings/{drawing_id}",
            params={"project_id": project_id},
            headers=headers
        )
    
    async def download_drawing_file(
        self,
        drawing_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> bytes:
        """Download drawing PDF file"""
        access_token = await self._get_access_token()
        url = f"{self.BASE_URL}/rest/{self.API_VERSION}/drawings/{drawing_id}/file"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Procore-Company-Id": company_id or self._get_company_id(),
        }
        
        params = {"project_id": project_id}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.content
    
    async def create_drawing_markup(
        self,
        drawing_id: str,
        project_id: str,
        markup_data: Dict[str, Any],
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create markup on drawing"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "POST",
            f"/drawings/{drawing_id}/markups",
            params={"project_id": project_id},
            json_data=markup_data,
            headers=headers
        )
    
    # Inspections Methods
    async def get_inspections(
        self,
        project_id: str,
        company_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List inspections for a project"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        request_params = {"project_id": project_id}
        if params:
            request_params.update(params)
        
        return await self._request("GET", "/inspections", params=request_params, headers=headers)
    
    async def get_inspection(
        self,
        inspection_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get inspection details"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "GET",
            f"/inspections/{inspection_id}",
            params={"project_id": project_id},
            headers=headers
        )
    
    async def create_inspection(
        self,
        project_id: str,
        inspection_data: Dict[str, Any],
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create inspection"""
        headers = {}
        if company_id:
            headers["Procore-Company-Id"] = company_id
        
        return await self._request(
            "POST",
            "/inspections",
            params={"project_id": project_id},
            json_data=inspection_data,
            headers=headers
        )
    
    # Documents Methods
    async def download_document(
        self,
        document_id: str,
        project_id: str,
        company_id: Optional[str] = None
    ) -> bytes:
        """Download document file"""
        access_token = await self._get_access_token()
        url = f"{self.BASE_URL}/rest/{self.API_VERSION}/documents/{document_id}/download"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Procore-Company-Id": company_id or self._get_company_id(),
        }
        
        params = {"project_id": project_id}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.content

