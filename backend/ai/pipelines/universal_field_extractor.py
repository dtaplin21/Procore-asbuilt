"""Universal field extraction for construction documents."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai.schemas.document_extraction_schemas import UniversalFields

logger = logging.getLogger(__name__)

UNIVERSAL_EXTRACTION_PROMPT = """
Extract these fields if present in the document:

- project_name
- project_number
- location_text
- date
- trade
- contractor
- document_title

If a field is missing, return null.

Respond as JSON matching exactly:
{
  "project_name": null,
  "project_number": null,
  "location_text": null,
  "date": null,
  "trade": null,
  "contractor": null,
  "document_title": null
}
"""

_UNIVERSAL_FIELD_KEYS = (
    "project_name",
    "project_number",
    "location_text",
    "date",
    "trade",
    "contractor",
    "document_title",
)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_universal_fields(document_text_or_description: str) -> UniversalFields:
    raw = _call_extraction_llm(document_text_or_description)
    try:
        return UniversalFields(**raw)
    except Exception as exc:
        logger.warning(
            "universal_field_extraction_invalid_response",
            extra={"error": str(exc), "raw": raw},
        )
        return UniversalFields()


def _empty_universal_fields_dict() -> dict[str, None]:
    return {key: None for key in _UNIVERSAL_FIELD_KEYS}


def _parse_extraction_payload(content: str) -> dict[str, Any]:
    trimmed = (content or "").strip()
    if not trimmed:
        return _empty_universal_fields_dict()

    candidates = [trimmed]
    block_match = _JSON_BLOCK_RE.search(trimmed)
    if block_match:
        candidates.insert(0, block_match.group(1))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return _sanitize_universal_fields_dict(parsed)

    return _empty_universal_fields_dict()


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value).strip() or None


def _sanitize_universal_fields_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _coerce_optional_str(raw.get(key))
        for key in _UNIVERSAL_FIELD_KEYS
    }


def _call_extraction_llm(content: str) -> dict[str, Any]:
    """
    Wire to the repo's existing OpenAI chat client.

    For text docs: use parsed text.
    For photos: use vision description or image model output.
    """
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return _empty_universal_fields_dict()

    if not getattr(settings, "openai_api_key", None):
        return _empty_universal_fields_dict()

    preview = (content or "").strip()
    if not preview:
        return _empty_universal_fields_dict()

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        f"{UNIVERSAL_EXTRACTION_PROMPT.strip()}\n\n"
        f"Document content or description:\n{preview[:4000]}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        message = (resp.choices[0].message.content or "").strip()
        return _parse_extraction_payload(message)
    except Exception as exc:
        logger.warning("universal_field_extractor_llm_failed", extra={"error": str(exc)})
        return _empty_universal_fields_dict()
