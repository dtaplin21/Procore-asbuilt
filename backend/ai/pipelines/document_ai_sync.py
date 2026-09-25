"""Synchronous Document AI ``process_document`` for single-page images."""

from __future__ import annotations

from typing import Any

from ai.pipelines.document_ai_client import document_processor_client
from ai.pipelines.document_ai_parser import words_from_proto_document
from ai.pipelines.document_text_extraction import PositionedWord
from config import document_ai_configured, settings


def process_image_bytes_document_ai(
    raw_bytes: bytes,
    *,
    mime_type: str = "image/png",
) -> list[PositionedWord]:
    """Run the configured OCR processor on one in-memory image."""
    if not document_ai_configured():
        raise RuntimeError("Document AI is not configured (see DOCUMENT_AI_* env vars)")

    from google.cloud import documentai

    processor_name = (settings.document_ai_processor_id or "").strip()
    if not processor_name:
        raise ValueError("DOCUMENT_AI_PROCESSOR_ID is not set")

    client = document_processor_client(settings.document_ai_location)
    raw_document = documentai.RawDocument(content=raw_bytes, mime_type=mime_type)
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
    result = client.process_document(request=request)
    return words_from_proto_document(result.document)


def document_proto_to_dict(document: Any) -> dict[str, Any]:
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(document._pb if hasattr(document, "_pb") else document)
