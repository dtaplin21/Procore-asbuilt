"""
Convenience entry point for application settings.

Single source of truth is :mod:`config` (Pydantic ``BaseSettings``). Typical environment
variables::

    PROCORE_CLIENT_ID
    PROCORE_CLIENT_SECRET
    PROCORE_REDIRECT_URI
    PROCORE_ENVIRONMENT
    FRONTEND_PUBLIC_URL

Import ``settings`` from either ``config`` or ``settings`` — they are the same object.
"""

from config import Settings, settings

__all__ = ["Settings", "settings"]
