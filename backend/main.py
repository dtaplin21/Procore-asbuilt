from observability.request_logging_middleware import RequestResponseLoggingMiddleware
from fastapi import FastAPI, Request
from observability.logging_config import configure_logging
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from errors import AppError
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
import logging
import httpx
from sqlalchemy.exc import SQLAlchemyError

configure_logging()

app = FastAPI(
    title="QC/QA AI Platform - Procore Integration",
    description="AI-powered Quality Control platform with Procore integration",
    version="1.0.0"
)

app.add_middleware(RequestResponseLoggingMiddleware)  # Add middleware

# ------------------------------------------------------------
# Error handling boundary (centralized exception handlers)
# ------------------------------------------------------------

logger = logging.getLogger("qcqa")

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.exception("AppError", extra={"error_code": exc.code})
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_response()})


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(httpx.RequestError)
async def httpx_request_error_handler(request: Request, exc: httpx.RequestError):
    logger.exception("Upstream request failed", extra={"url": str(getattr(exc.request, "url", ""))})
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "UPSTREAM_UNREACHABLE",
                "message": "Failed to reach upstream service",
            }
        },
    )


@app.exception_handler(httpx.HTTPStatusError)
async def httpx_status_error_handler(request: Request, exc: httpx.HTTPStatusError):
    # Procore (or other upstream) returned a non-2xx response.
    status = exc.response.status_code if exc.response is not None else 502
    logger.exception("Upstream returned error status", extra={"status": status, "url": str(exc.request.url)})
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "UPSTREAM_ERROR",
                "message": "Upstream service returned an error",
                "upstream_status": status,
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "DB_ERROR",
                "message": "Database operation failed",
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
            }
        },
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

