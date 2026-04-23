"""Shared multipart coalescing for drawing upload_intent / uploadIntent form fields."""

from __future__ import annotations


def coalesce_upload_intent_form(
    upload_intent: str | None,
    uploadIntent: str | None,
) -> str | None:
    """
    Prefer snake_case `upload_intent` when both multipart fields are present.
    Strips whitespace; maps empty string to None (avoids DB check surprises).
    Returns a raw string to validate: None, "master", "sub", or any other string (caller returns 400).
    """
    raw = upload_intent if upload_intent is not None else uploadIntent
    if raw is not None:
        raw = raw.strip()
    if raw == "":
        return None
    return raw
