from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

class Settings(BaseSettings):
    # Use psycopg v3 driver by default (matches requirements.txt: psycopg[binary])
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/procore_int"
    procore_client_id: Optional[str] = None
    procore_client_secret: Optional[str] = None
    procore_redirect_uri: str = "http://localhost:2000/api/procore/oauth/callback"
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

