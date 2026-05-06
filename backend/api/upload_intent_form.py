"""Shared multipart coalescing for drawing upload_intent / uploadIntent form fields."""

from __future__ import annotations

UPLOAD_INTENT_OPENAPI_DESCRIPTION = (
    "Drawing role: `master` — canonical workspace sheet (sets `projects.master_drawing_id` "
    "and reconciles intents). `sub` — sub sheet only. Omit or empty — no explicit intent on the "
    "new row; **if the project has no master yet** (`master_drawing_id` is null), this upload "
    "becomes the master automatically (first-upload onboarding); otherwise the project's master "
    "is unchanged."
)


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
