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

Application environment::

    APP_ENV                     # development | production (production on Render)
    DATABASE_SSL_INSECURE_DEV   # optional; local dev only — skip Postgres TLS cert verification (cloud DB)
    DATABASE_DISABLE_SSL_FOR_LOCALHOST  # default true in dev — sslmode=disable for localhost DB (non-TLS Postgres)
    OPENAI_API_KEY              # API host only — required for inspection/GPT features (beta)
    OPENAI_CHAT_MODEL           # optional — defaults to gpt-4o-mini
    USE_MODEL_ALIGNMENT         # optional — "true" to try learned matcher before ORB (see compute_alignment_transform)
"""

from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Literal, Optional


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
    #: Required on the API host for inspection mapping / GPT calls (set ``OPENAI_API_KEY`` in env or ``backend/.env``).
    openai_api_key: Optional[str] = Field(default=None, description="OPENAI_API_KEY")
    #: Chat model for inspection pipeline (optional). Env: ``OPENAI_CHAT_MODEL``.
    openai_chat_model: str = Field(default="gpt-4o-mini", description="OPENAI_CHAT_MODEL")
    redis_url: Optional[str] = None
    #: ``development`` | ``production`` — use ``production`` on Render. Gates dev-only DB TLS workarounds.
    app_env: str = Field(default="development", description="APP_ENV")
    #: DEV ONLY: skip Postgres server certificate verification (fixes some macOS/Python↔cloud DB TLS issues).
    #: Forced off when ``app_env`` is ``production``. Never enable on deployed API.
    database_ssl_insecure_dev: bool = Field(default=False, description="DATABASE_SSL_INSECURE_DEV")
    #: When ``APP_ENV`` is not ``production`` and ``DATABASE_URL`` host is localhost (or unix socket),
    #: pass ``sslmode=disable`` so non-TLS local Postgres works. Set false if you use an SSH tunnel
    #: to a remote DB and the URL points at ``127.0.0.1``. Env: ``DATABASE_DISABLE_SSL_FOR_LOCALHOST``.
    database_disable_ssl_for_localhost: bool = Field(
        default=True,
        description="DATABASE_DISABLE_SSL_FOR_LOCALHOST",
    )

    #: When true, try learned matcher first in :meth:`DrawingComparisonService.compute_alignment_transform`;
    #: on failure or if unavailable, fall back to ORB/homography. Env: ``USE_MODEL_ALIGNMENT=true``.
    use_model_alignment: bool = Field(
        default=False,
        description="USE_MODEL_ALIGNMENT",
    )

    # In some environments (CI, sandboxes), extra env vars may be present.
    # Ignore unknown keys instead of erroring at import time.
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("openai_chat_model", mode="before")
    @classmethod
    def _strip_openai_chat_model(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s if s else "gpt-4o-mini"
        return v

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def _empty_openai_key_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("use_model_alignment", mode="before")
    @classmethod
    def _coerce_use_model_alignment(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower() == "true"
        return v

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

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def _never_insecure_db_ssl_in_production(self) -> "Settings":
        if self.app_env == "production" and self.database_ssl_insecure_dev:
            object.__setattr__(self, "database_ssl_insecure_dev", False)
        return self

    @field_validator("procore_environment", mode="before")
    @classmethod
    def _normalize_procore_environment(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


settings = Settings()


def _database_host_is_local_loopback(database_url: str) -> bool:
    """True when ``DATABASE_URL`` targets this machine (non-TLS Docker/Homebrew Postgres)."""
    u = database_url.strip()
    if u.startswith("postgresql+psycopg://"):
        u = "postgresql://" + u[len("postgresql+psycopg://") :]
    elif u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    try:
        parsed = urlparse(u)
    except Exception:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return True
    return host in ("localhost", "127.0.0.1", "::1")


def sqlalchemy_connect_args(s: Optional[Settings] = None) -> dict[str, Any]:
    """
    Extra arguments for SQLAlchemy/psycopg ``create_engine(connect_args=...)``.

    In **development**, when the DB host is localhost (or unix-socket style URL) and
    ``DATABASE_DISABLE_SSL_FOR_LOCALHOST`` is true (default), ``sslmode=disable`` is set so
    typical local Postgres without TLS does not fail with "SSL was required".

    When ``DATABASE_SSL_INSECURE_DEV=true`` and ``APP_ENV`` is not ``production`` (and the
    localhost shortcut above did not apply), TLS is still used but server certificate
    verification is skipped — for local dev against **cloud** Postgres when verification fails.

    Psycopg turns connection kwargs into a libpq conninfo string. ``ssl_context`` is not a libpq
    keyword and does not disable verification in this stack; use libpq's ``sslrootcert`` instead.
    """
    cfg = s or settings
    if cfg.app_env != "production" and cfg.database_disable_ssl_for_localhost:
        if _database_host_is_local_loopback(cfg.database_url):
            return {"sslmode": "disable"}
    if cfg.app_env == "production" or not cfg.database_ssl_insecure_dev:
        return {}
    return {
        # Override URL modes like verify-full / verify-ca from managed providers.
        "sslmode": "require",
        # Stops libpq from loading a root CA (including ~/.postgresql/root.crt), so `require`
        # stays "encrypt only" per Table 32.1 in the libpq SSL docs. Requires modern libpq (e.g. PG16+).
        "sslrootcert": "disable",
    }


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

