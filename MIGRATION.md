# FastAPI Migration Guide

This document outlines the migration from Express.js to FastAPI.

## What Changed

### Backend
- **Before**: Express.js (Node.js/TypeScript) in `server/` directory
- **After**: FastAPI (Python) in `backend/` directory

### Frontend
- **No changes**: React frontend remains the same
- API calls now proxy through Vite dev server to FastAPI backend

## Setup Instructions

### 1. Install Python Dependencies

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your actual values
```

### 3. Initialize Database

```bash
cd backend
python -c "from database import init_db; init_db()"
```

### 4. Run the Application

#### Option A: Run Backend and Frontend Separately

**Terminal 1 - Backend:**
```bash
cd backend
./run.sh
# Or: uvicorn main:app --reload --host 0.0.0.0 --port 2000
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

#### Option B: Use Concurrent Scripts (if installed)

```bash
npm install -g concurrently
npm run dev:all
```

## API Endpoints

All endpoints remain the same:
- `GET /api/dashboard/stats`
- `GET /api/projects`
- `GET /api/inspections`
- `GET /api/objects`
- `GET /api/insights`
- `GET /api/procore/status`

## API Documentation

FastAPI provides automatic API documentation:
- **Swagger UI**: http://localhost:2000/docs
- **ReDoc**: http://localhost:2000/redoc

## Differences from Express.js

1. **Type Safety**: Pydantic models provide runtime validation
2. **Auto Documentation**: FastAPI generates OpenAPI docs automatically
3. **Async/Await**: All routes are async by default
4. **Dependency Injection**: Database sessions injected via `Depends(get_db)`

## Next Steps

1. Implement Procore OAuth flow in `backend/api/routes/procore.py`
2. Add AI agent implementations in `backend/ai/agents/`
3. Set up webhook handlers for Procore events
4. Add drawing markup endpoints
5. Implement mobile API endpoints

