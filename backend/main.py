from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.routes import (
    dashboard,
    projects,
    submittals,
    rfis,
    inspections,
    objects,
    insights,
    procore,
    procore_auth
)
from database import init_db
import os

app = FastAPI(
    title="QC/QA AI Platform - Procore Integration",
    description="AI-powered Quality Control platform with Procore integration",
    version="1.0.0"
)

# CORS middleware - allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:2000",  # Production
        "http://127.0.0.1:5173",
        "http://127.0.0.1:2000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(submittals.router)
app.include_router(rfis.router)
app.include_router(inspections.router)
app.include_router(objects.router)
app.include_router(insights.router)
app.include_router(procore.router)
app.include_router(procore_auth.router)  # Authentication routes

# Serve static files in production (if needed)
# static_dir = os.path.join(os.path.dirname(__file__), "..", "dist", "public")
# if os.path.exists(static_dir):
#     app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "qc-qa-platform"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "QC/QA AI Platform API",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "2000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)

