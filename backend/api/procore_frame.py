"""Allow Procore to embed this app. frame-ancestors is the allowlist; X-Frame-Options is not sent."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Sandbox first, then the production app and the other Procore hostnames that embed apps.
PROCORE_FRAME_ANCESTORS = (
    "https://sandbox.procore.com",
    "https://app.procore.com",
    "https://*.procore.com",
    "https://*.procore.gov",
)


def frame_ancestors_policy() -> str:
    return "frame-ancestors " + " ".join(PROCORE_FRAME_ANCESTORS)


class ProcoreFrameAncestorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = frame_ancestors_policy()
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        return response
