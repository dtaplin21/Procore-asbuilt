"""Shared multipart coalescing for drawing upload_intent / uploadIntent form fields."""

from __future__ import annotations

from typing import Literal

UploadIntent = Literal["master", "sub"]

UPLOAD_INTENT_OPENAPI_DESCRIPTION = (
    "Drawing role: `master` — canonical workspace sheet (sets `projects.master_drawing_id` "
    "and reconciles intents). `sub` — sub sheet only. Omit or empty — no explicit intent on the "
    "new row; **if the project has no master yet** (`master_drawing_id` is null), this upload "
    "becomes the master automatically (first-upload onboarding); otherwise the project's master "
    "is unchanged."
)


def drawing_has_sub_upload_intent(drawing: object) -> bool:
    """
    Return True only when the drawing was uploaded with explicit ``sub`` intent.

    ``upload_intent`` is nullable on legacy rows—use this (or ``== "sub"``) for
    auto-compare and similar hooks. Do **not** use truthy checks (e.g.
    ``if drawing.upload_intent:``), which would mis-handle ``None`` and are
    wrong for ``master``.
    """
    return getattr(drawing, "upload_intent", None) == "sub"


def coalesce_upload_intent_form(
    upload_intent: str | None,
    uploadIntent: str | None,
) -> str | None:
    """
    Prefer snake_case `upload_intent` when both multipart fields are present.
    Prefer :func:`parse_upload_intent_form_fields` for validated ``UploadIntent | None``.
    Returns a raw string (after strip) to validate: ``None``, ``"master"``, ``"sub"``, or any
    other string (caller / :func:`parse_upload_intent_form_fields` returns 400).
    """
    raw = upload_intent if upload_intent is not None else uploadIntent
    if raw is not None:
        raw = raw.strip()
    if raw == "":
        return None
    return raw


def parse_upload_intent_form_fields(
    upload_intent: str | None,
    uploadIntent: str | None,
) -> UploadIntent | None:
    """
    Normalized ``UploadIntent`` after multipart coalescing.

    Raises ``ValueError`` with a stable message if the string is non-empty but not
    ``master`` / ``sub`` (callers map to HTTP 400).
    """
    raw = coalesce_upload_intent_form(upload_intent, uploadIntent)
    if raw is None:
        return None
    if raw == "master":
        return "master"
    if raw == "sub":
        return "sub"
    raise ValueError("upload_intent must be one of: master, sub")
