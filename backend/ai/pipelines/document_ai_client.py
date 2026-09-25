"""Document AI API client factory (batch OCR — see Notes/ai google implementation.md)."""

from __future__ import annotations

from google.api_core.client_options import ClientOptions
from google.cloud import documentai


def document_ai_api_endpoint(location: str) -> str:
    loc = location.strip().lower()
    if loc not in ("us", "eu"):
        raise ValueError(f"DOCUMENT_AI_LOCATION must be us or eu, got {location!r}")
    return f"{loc}-documentai.googleapis.com"


def document_processor_client(location: str) -> documentai.DocumentProcessorServiceClient:
    endpoint = document_ai_api_endpoint(location)
    return documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=endpoint),
    )
