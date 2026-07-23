"""
OpenAI vision helpers for image OCR and other image→text tasks.

Images are base64-encoded into data URLs and sent via ``chat.completions``
with an ``image_url`` content part. ``extract_plain_text_from_image`` is the
OCR fallback used when Tesseract is unavailable or ``OCR_BACKEND=openai_vision``.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OCR_PROMPT = """Extract all readable text from this image exactly as it appears.
Return only the plain text transcription with no commentary, markdown, or JSON.
Preserve line breaks where they appear in the document."""

_SUFFIX_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
}


def _mime_type_for_path(path: Path) -> str:
    return _SUFFIX_MIME.get(path.suffix.lower(), "image/jpeg")


def encode_image_as_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Base64-encode raw image bytes into an OpenAI-compatible data URL."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _load_image(
    *,
    file_path: str | Path | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> tuple[bytes, str]:
    if image_bytes is not None:
        if mime_type:
            return image_bytes, mime_type
        if file_path is not None:
            return image_bytes, _mime_type_for_path(Path(file_path))
        return image_bytes, "image/jpeg"

    if file_path is None:
        raise ValueError("Provide file_path or image_bytes")

    path = Path(file_path)
    return path.read_bytes(), mime_type or _mime_type_for_path(path)


def _vision_chat_completion(
    *,
    image_data_url: str,
    prompt: str,
    max_tokens: int = 4096,
) -> str:
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return ""

    if not getattr(settings, "openai_api_key", None):
        return ""

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url, "detail": "high"},
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.warning("openai_vision_chat_failed", extra={"error": str(exc)})
        return ""

    return (resp.choices[0].message.content or "").strip()


def extract_plain_text_from_image(
    *,
    file_path: str | Path | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> str:
    """
    OCR fallback: return all readable plain text from a raster image.

    Accepts either a filesystem path or in-memory bytes. Returns an empty
    string when OpenAI is unavailable or the call fails.
    """
    try:
        raw_bytes, resolved_mime = _load_image(
            file_path=file_path,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
    except (OSError, ValueError) as exc:
        logger.warning("openai_vision_image_load_failed", extra={"error": str(exc)})
        return ""

    data_url = encode_image_as_data_url(raw_bytes, resolved_mime)
    return _vision_chat_completion(image_data_url=data_url, prompt=OCR_PROMPT)
