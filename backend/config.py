"""
Application settings via environment variables (Pydantic Settings).

Procore OAuth (and related) env keys read here — use the same values in the Procore app
registration (especially ``PROCORE_REDIRECT_URI``)::

    PROCORE_CLIENT_ID
    PROCORE_CLIENT_SECRET
    PROCORE_REDIRECT_URI    # must match authorize + token exchange redirect_uri exactly
    PROCORE_ENVIRONMENT     # production | sandbox

Frontend (post-OAuth browser redirect)::

    FRONTEND_PUBLIC_URL     # origin only, e.g. https://app.example.com

CORS (browser → API). For production set an explicit allowlist; when unset, only local dev
origins are used::

    CORS_ALLOW_ORIGINS      # comma-separated, e.g. https://app.example.com
                            # ``FRONTEND_PUBLIC_URL`` is merged in if not already listed.

``backend/services/procore_oauth`` uses ``settings.procore_*`` for authorize URL and token
exchange so redirect_uri is never hardcoded there.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

class Settings(BaseSettings):
    # Use psycopg v3 driver by default (matches requirements.txt: psycopg[binary])
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/procore_int"
    procore_client_id: Optional[str] = None
    procore_client_secret: Optional[str] = None
    procore_redirect_uri: str = "http://localhost:2000/api/procore/oauth/callback"
    #: SPA origin for redirects after OAuth (path /settings is appended in procore_auth).
    frontend_public_url: str = Field(
        default="http://localhost:5173",
        description="Browser-accessible frontend origin (no path), e.g. https://app.example.com",
    )
    #: Comma-separated browser origins allowed for CORS. Empty → local dev defaults only.
    cors_allow_origins: str = Field(
        default="",
        description="Comma-separated origins (e.g. https://app.example.com). Empty uses built-in localhost list.",
    )
    # Sandbox Developer Portal apps must use login-sandbox + sandbox API, not production hosts.
    procore_environment: Literal["production", "sandbox"] = "production"
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    redis_url: Optional[str] = None
    
    # In some environments (CI, sandboxes), extra env vars may be present.
    # Ignore unknown keys instead of erroring at import time.
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _ensure_psycopg3_driver_scheme(cls, v: object) -> object:
        """
        SQLAlchemy uses psycopg2 for plain postgresql:// URLs. This project ships psycopg v3
        only (psycopg[binary]). Render and other hosts often supply postgres:// or
        postgresql:// — rewrite so create_engine loads psycopg3 without psycopg2.
        """
        if not isinstance(v, str):
            return v
        s = v.strip()
        if s.startswith("postgresql+psycopg://"):
            return s
        if s.startswith("postgres://"):
            return "postgresql+psycopg://" + s[len("postgres://") :]
        if s.startswith("postgresql://"):
            return "postgresql+psycopg://" + s[len("postgresql://") :]
        return s

    @field_validator("procore_environment", mode="before")
    @classmethod
    def _normalize_procore_environment(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


settings = Settings()


_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:2000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:2000",
]


def cors_allowed_origins() -> list[str]:
    """
    Origins for FastAPI CORSMiddleware.

    If ``CORS_ALLOW_ORIGINS`` is set, only those entries are used (comma-separated), plus
    ``FRONTEND_PUBLIC_URL`` if missing. If unset, the local development list is used.
    """
    raw = settings.cors_allow_origins.strip()
    if raw:
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    else:
        origins = list(_DEV_CORS_ORIGINS)
    front = settings.frontend_public_url.strip().rstrip("/")
    if front and front not in origins:
        origins.append(front)
    return origins


def procore_authorization_url() -> str:
    if settings.procore_environment == "sandbox":
        return "https://login-sandbox.procore.com/oauth/authorize"
    return "https://login.procore.com/oauth/authorize"


def procore_token_url() -> str:
    if settings.procore_environment == "sandbox":
        return "https://login-sandbox.procore.com/oauth/token"
    return "https://login.procore.com/oauth/token"


def procore_api_base_url() -> str:
    if settings.procore_environment == "sandbox":
        return "https://sandbox.procore.com"
    return "https://api.procore.com"

