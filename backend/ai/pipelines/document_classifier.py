"""Document classifier for supported construction document types.

If confidence is below threshold, return UNKNOWN so the wrong type-specific extractor
does not run.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai.schemas.document_extraction_schemas import DocumentClassification, DocumentType

logger = logging.getLogger(__name__)

CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.60

CLASSIFY_PROMPT = """
Classify this construction document into exactly one type:

- inspection_report
- field_photo
- master_drawing
- unknown

Use unknown if it clearly does not fit the supported types or if there is not enough
information.

Respond as JSON:
{
  "document_type": "inspection_report | field_photo | master_drawing | unknown",
  "confidence": 0.0
}
"""

_SUPPORTED_TYPES = {t.value for t in DocumentType}
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def normalize_classification(
    classification: DocumentClassification,
) -> DocumentClassification:
    """Force UNKNOWN when model confidence is below the classification threshold."""
    if classification.confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
        return classification.model_copy(update={"document_type": DocumentType.UNKNOWN})
    return classification


def classify_document(document_text_or_description: str) -> DocumentClassification:
    raw = _call_classifier_llm(document_text_or_description)
    try:
        classification = DocumentClassification(**raw)
    except Exception as exc:
        logger.warning(
            "document_classification_invalid_response",
            extra={"error": str(exc), "raw": raw},
        )
        classification = DocumentClassification(
            document_type=DocumentType.UNKNOWN,
            confidence=0.0,
        )
    return normalize_classification(classification)


def _parse_classifier_payload(content: str) -> dict[str, Any]:
    trimmed = (content or "").strip()
    if not trimmed:
        return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}

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
            return _sanitize_classifier_dict(parsed)

    return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}


def _sanitize_classifier_dict(raw: dict[str, Any]) -> dict[str, Any]:
    document_type = str(raw.get("document_type", DocumentType.UNKNOWN.value)).strip().lower()
    if document_type not in _SUPPORTED_TYPES:
        document_type = DocumentType.UNKNOWN.value

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    return {"document_type": document_type, "confidence": confidence}


def _call_classifier_llm(content: str) -> dict[str, Any]:
    """
    Wire to the repo's existing OpenAI chat client.

    For text-bearing docs: send extracted text.
    For photos/drawings: send an image description or vision output.
    """
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}

    if not getattr(settings, "openai_api_key", None):
        return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}

    preview = (content or "").strip()
    if not preview:
        return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        f"{CLASSIFY_PROMPT.strip()}\n\n"
        f"Document content or description:\n{preview[:4000]}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=128,
        )
        message = (resp.choices[0].message.content or "").strip()
        return _parse_classifier_payload(message)
    except Exception as exc:
        logger.warning("document_classifier_llm_failed", extra={"error": str(exc)})
        return {"document_type": DocumentType.UNKNOWN.value, "confidence": 0.0}
