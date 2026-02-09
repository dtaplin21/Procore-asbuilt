from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost/procore_integrator"
    procore_client_id: Optional[str] = None
    procore_client_secret: Optional[str] = None
    procore_redirect_uri: str = "http://localhost:2000/api/procore/oauth/callback"
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    redis_url: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()

