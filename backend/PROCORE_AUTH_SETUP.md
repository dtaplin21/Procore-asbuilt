# Procore Authentication Foundation - Setup Guide

## ✅ What's Been Implemented

### 1. Database Models
- **`ProcoreToken`** - Stores OAuth tokens (access_token, refresh_token, expiration)
- **`ProcoreUser`** - Stores synced user info (email, name, company_ids, project_ids)

### 2. Services
- **`ProcoreOAuth`** (`services/procore_oauth.py`) - Handles OAuth flow
  - Generate authorization URLs
  - Exchange code for tokens
  - Refresh expired tokens
  - Get user info from Procore
  - Sync user data
  
- **`ProcoreAPIClient`** (`services/procore_client.py`) - Main API client
  - Automatic token refresh
  - All Procore API endpoints (Projects, Submittals, RFIs, Drawings, Inspections, etc.)
  - Company ID handling per request

### 3. API Routes (`api/routes/procore_auth.py`)
- `GET /api/procore/oauth/authorize` - Start OAuth flow
- `GET /api/procore/oauth/callback` - Handle OAuth callback
- `POST /api/procore/oauth/refresh` - Refresh token
- `GET /api/procore/status` - Check connection status
- `GET /api/procore/me` - Get current user info
- `GET /api/procore/companies` - List user's companies
- `GET /api/procore/projects` - List accessible projects
- `GET /api/procore/projects/{id}` - Get project details
- `GET /api/procore/projects/{id}/team` - Get project team
- `POST /api/procore/disconnect` - Disconnect Procore account

## 🔧 Configuration Required

### 1. Environment Variables
Add to `backend/.env`:

```env
PROCORE_CLIENT_ID=your_procore_client_id
PROCORE_CLIENT_SECRET=your_procore_client_secret
PROCORE_REDIRECT_URI=http://localhost:2000/api/procore/oauth/callback
```

### 2. Procore App Registration
1. Go to https://dev-portal-staging1.procoretech-qa.com (or production portal)
2. Create a new app
3. Set redirect URI: `http://localhost:2000/api/procore/oauth/callback`
4. Copy Client ID and Client Secret
5. Add to `.env` file

### 3. Database Migration
Run to create new tables:

```bash
cd backend
python -c "from database import init_db; init_db()"
```

## 🚀 Usage Examples

### Frontend - Connect to Procore
```typescript
// In your React component
const handleConnectProcore = () => {
  window.location.href = '/api/procore/oauth/authorize';
};

// After callback, check status
const { data: status } = useQuery({
  queryKey: ['/api/procore/status', { user_id: currentUserId }]
});
```

### Backend - Use Procore Client
```python
from services.procore_client import ProcoreAPIClient
from database import SessionLocal

db = SessionLocal()
async with ProcoreAPIClient(db, user_id="123") as client:
    # Get projects
    projects = await client.get_projects()
    
    # Get submittals
    submittals = await client.get_submittals(project_id="456")
    
    # Create markup on drawing
    markup = await client.create_drawing_markup(
        drawing_id="789",
        project_id="456",
        markup_data={"type": "cloud", "coordinates": [...]}
    )
```

## 🔐 Security Notes

### Token Storage
- Tokens are stored in database (should be encrypted in production)
- Consider using encryption for `access_token` and `refresh_token` columns
- Use environment variables for client secrets (never commit)

### State Management
- Currently using in-memory dict for OAuth state
- **Production**: Use Redis or database for state storage
- State should expire after 10 minutes

### Token Refresh
- Tokens automatically refresh when expired (within 5 minutes of expiration)
- Refresh tokens are long-lived but should be rotated periodically
- Handle refresh failures gracefully (prompt re-authentication)

## 📋 Next Steps

1. **Add Encryption** - Encrypt tokens in database
2. **Session Management** - Link OAuth flow to user sessions
3. **Error Handling** - Better error messages and retry logic
4. **Webhooks** - Set up webhook endpoints for real-time updates
5. **Rate Limiting** - Implement Procore API rate limit handling
6. **Caching** - Cache frequently accessed data (projects, companies)

## 🧪 Testing

### Test OAuth Flow
1. Start backend: `uvicorn main:app --reload`
2. Visit: `http://localhost:2000/api/procore/oauth/authorize`
3. Complete Procore login
4. Should redirect to frontend with `procore_connected=true`

### Test API Calls
```bash
# Get status
curl "http://localhost:2000/api/procore/status?user_id=123"

# Get projects
curl "http://localhost:2000/api/procore/projects?user_id=123"

# Get companies
curl "http://localhost:2000/api/procore/companies?user_id=123"
```

## 📚 Procore API Documentation
- Base URL: `https://api.procore.com/rest/v1.0`
- Auth: OAuth 2.0 Bearer tokens
- Required Header: `Procore-Company-Id` for most endpoints
- Rate Limits: Check Procore docs for current limits

