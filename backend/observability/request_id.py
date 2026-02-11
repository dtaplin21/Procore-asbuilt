from __future__ import annotations

from contextvars import ContextVar
from typing import Optional, Any


# Global variable that stores every request
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

def set_request_id(request_id: str) -> Any:
    return _request_id_var.set(request_id)

def reset_request_id(token: Any) -> None:
    _request_id_var.reset(token)

def get_request_id() -> Optional[str]:
    return _request_id_var.get()