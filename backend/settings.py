"""
Convenience entry point for application settings.

Single source of truth is :mod:`config` (Pydantic ``BaseSettings``). Typical environment
variables::

    PROCORE_CLIENT_ID
    PROCORE_CLIENT_SECRET
    PROCORE_REDIRECT_URI
    PROCORE_ENVIRONMENT
    FRONTEND_PUBLIC_URL
    CORS_ALLOW_ORIGINS     # production: comma-separated API CORS origins
    APP_ENV                # development | production (``production`` on Render)
    DATABASE_SSL_INSECURE_DEV  # local dev only — skip Postgres TLS cert verify
    OPENAI_API_KEY         # API host — inspection / GPT (use ``backend/.env`` locally, not repo root)
    OPENAI_CHAT_MODEL      # optional — defaults to gpt-4o-mini

Import ``settings`` from either ``config`` or ``settings`` — they are the same object.
See also ``config.cors_allowed_origins()`` used by ``main`` for CORSMiddleware.
"""

from config import Settings, cors_allowed_origins, settings, sqlalchemy_connect_args

__all__ = ["Settings", "cors_allowed_origins", "settings", "sqlalchemy_connect_args"]
