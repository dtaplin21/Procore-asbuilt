from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    """
    Base typed error for the application.
    These should be raised from services/business logic and formatted at the API boundary.
    """

    message: str
    status_code: int = 500
    code: str = "APP_ERROR"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


# -----------------------------
# Procore / upstream errors
# -----------------------------


class ProcoreNotConnected(AppError):
    def __init__(self, message: str = "No Procore connection found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=404, code="PROCORE_NOT_CONNECTED", details=details or {})


class ProcoreAuthExpired(AppError):
    def __init__(self, message: str = "Procore authorization expired", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=401, code="PROCORE_AUTH_EXPIRED", details=details or {})


class ProcoreRateLimited(AppError):
    def __init__(
        self,
        message: str = "Procore rate limited",
        retry_after_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        d = dict(details or {})
        if retry_after_seconds is not None:
            d["retry_after_seconds"] = retry_after_seconds
        super().__init__(message=message, status_code=429, code="PROCORE_RATE_LIMITED", details=d)


class ExternalServiceError(AppError):
    def __init__(self, message: str = "Upstream service error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=502, code="UPSTREAM_ERROR", details=details or {})


class ProcoreOAuthError(AppError):
    def __init__(self, message: str = "Procore OAuth error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, code="PROCORE_OAUTH_ERROR", details=details or {})


