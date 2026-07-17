"""Helpers to keep backend-only numeric scores out of frontend API payloads."""

from __future__ import annotations

from typing import Any

FORBIDDEN_FRONTEND_SCORE_KEYS = frozenset(
    {
        "confidence",
        "score",
        "classification_confidence",
        "match_score",
        "similarity",
        "percentage",
    }
)


def sanitize_frontend_dict(value: Any) -> Any:
    """Remove backend-only score fields from dict payloads sent to the client."""
    if not isinstance(value, dict):
        return value

    return {
        key: sanitized
        for key, item in value.items()
        if key not in FORBIDDEN_FRONTEND_SCORE_KEYS
        for sanitized in (sanitize_frontend_dict(item),)
    }


def contains_forbidden_frontend_score_fields(value: Any, *, path: str = "") -> list[str]:
    """Return dotted paths of forbidden score keys found in a JSON-like structure."""
    found: list[str] = []

    if isinstance(value, dict):
        for key, item in value.items():
            current = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FRONTEND_SCORE_KEYS:
                found.append(current)
            found.extend(contains_forbidden_frontend_score_fields(item, path=current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            current = f"{path}[{index}]"
            found.extend(contains_forbidden_frontend_score_fields(item, path=current))

    return found
