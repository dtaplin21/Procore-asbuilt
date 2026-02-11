from __future__ import annotations

import logging
import time
import uuid

from typing import Optional, Any, Awaitable, Callable, Dict

# NOTE: We intentionally avoid importing `starlette.types` here because some editors/linters
# can run against a different interpreter than `backend/venv` and fail to resolve Starlette.
# These aliases match the standard ASGI callable signatures used by Starlette/FastAPI.
Scope = Dict[str, Any]
Message = Dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

from .request_id import set_request_id, reset_request_id

logger = logging.getLogger("qcqa.request")

class RequestResponseLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Ensure state exists
        scope.setdefault("state", {})
        
        # Extract request info
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")
        
        # Get or generate request ID
        request_id = _get_header(scope, b"x-request-id") or str(uuid.uuid4())
        
        # Store request ID
        scope["state"]["request_id"] = request_id
        token = set_request_id(request_id)
        
        # Start timer
        start = time.perf_counter()
        status_code: Optional[int] = None
        
        # Wrap send to capture status code and add header
        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                
                # Add X-Request-Id header to response
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("utf-8")))
                message["headers"] = headers
            
            await send(message)
        
        try:
            # Process request
            await self.app(scope, receive, send_wrapper)
            
        except Exception:
            # Log unhandled exceptions
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                }
            )
            raise
        
        finally:
            # Log request completion
            duration_ms = int((time.perf_counter() - start) * 1000)
            
            logger.info(
                "request_complete",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                }
            )
            
            # Clean up request ID
            reset_request_id(token)


def _get_header(scope: Scope, header_name: bytes) -> Optional[str]:
    """Extract header value from ASGI scope"""
    for k, v in scope.get("headers") or []:
        if k.lower() == header_name:
            try:
                return v.decode("utf-8")
            except Exception:
                return None
    return None