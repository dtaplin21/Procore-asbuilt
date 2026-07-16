"""Type-specific extraction dispatcher.

Validation failures route to review queue instead of crashing or silently storing bad data.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai.schemas.document_extraction_schemas import (
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
    TYPE_SPECIFIC_SCHEMAS,
)
from services.review_queue import add_to_review_queue

logger = logging.getLogger(__name__)

TypeSpecificFields = InspectionReportFields | FieldPhotoFields | MasterDrawingFields

TYPE_SPECIFIC_PROMPTS = {
    DocumentType.INSPECTION_REPORT: """
Extract:
- inspection_name
- inspection_status
- items_inspected as a list
- pass_fail_result
- assignees as a list
- inspection_notes as a list

Return JSON only.
""",
    DocumentType.FIELD_PHOTO: """
Extract from the photo or photo description:
- visible_objects as a list
- visible_text as a list
- environment
- utility_type
- possible_location_clues as a list
- camera_perspective

Return JSON only.
""",
    DocumentType.MASTER_DRAWING: """
Extract from the master drawing or drawing description:
- sheet_number
- sheet_title
- discipline
- drawing_labels as a list
- utility_symbols as a list
- areas_or_zones as a list

Return JSON only.
""",
}

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_type_specific_fields(
    document_type: DocumentType,
    content: str,
    session: Session,
    file_id: str,
) -> TypeSpecificFields | None:
    if document_type not in TYPE_SPECIFIC_SCHEMAS:
        return None

    schema_cls = TYPE_SPECIFIC_SCHEMAS[document_type]
    prompt = TYPE_SPECIFIC_PROMPTS[document_type]
    raw = _call_extraction_llm(content, prompt)

    try:
        return schema_cls(**raw)
    except ValidationError as exc:
        logger.warning(
            "type_specific_extraction_validation_failed",
            extra={
                "file_id": file_id,
                "document_type": document_type.value,
                "error": str(exc),
                "raw": raw,
            },
        )
        add_to_review_queue(
            session,
            file_id=file_id,
            reason="extraction_validation_failed",
            document_type_guess=document_type.value,
        )
        return None


def _parse_extraction_payload(content: str) -> dict[str, Any]:
    trimmed = (content or "").strip()
    if not trimmed:
        return {}

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
            return parsed

    return {}


def _call_extraction_llm(content: str, prompt: str) -> dict[str, Any]:
    """
    Wire to the repo's existing OpenAI chat client.

    For text docs: use parsed text.
    For photos/drawings: use vision description or image model output.
    """
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return {}

    if not getattr(settings, "openai_api_key", None):
        return {}

    preview = (content or "").strip()
    if not preview:
        return {}

    client = OpenAI(api_key=settings.openai_api_key)
    full_prompt = (
        f"{prompt.strip()}\n\n"
        f"Document content or description:\n{preview[:4000]}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": full_prompt}],
            max_tokens=512,
        )
        message = (resp.choices[0].message.content or "").strip()
        return _parse_extraction_payload(message)
    except Exception as exc:
        logger.warning("type_specific_extractor_llm_failed", extra={"error": str(exc)})
        return {}
