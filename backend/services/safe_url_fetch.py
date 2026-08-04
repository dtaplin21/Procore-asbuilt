"""Allowlisted HTTP(S) fetch with SSRF guards for PDF link enrichment.

Network and security rules live here — not in the AI pipeline module.
Allowed hosts come from ``config.pdf_link_follow_allowed_host_suffixes()``.

Followed PDF and image attachments are always OCR'd (never native PDF text layers).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import tempfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from ai.pipelines.document_text_extraction import extract_document_via_ocr
from config import pdf_link_follow_allowed_host_suffixes, settings

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10.0


def max_response_bytes() -> int:
    """Configured cap for a single external link fetch (default 20 MiB)."""
    return int(settings.pdf_link_follow_max_response_bytes)


@dataclass(frozen=True)
class SafeFetchResult:
    ok: bool
    url: str
    status_code: int | None = None
    content_type: str | None = None
    content_disposition: str | None = None
    body: bytes = b""
    error: str | None = None


@dataclass(frozen=True)
class UrlAttachmentFetch:
    text: str
    error: str | None
    filename: str
    pages: int


def is_allowed_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    suffixes = pdf_link_follow_allowed_host_suffixes()
    return any(host == suffix or host.endswith(f".{suffix}") or host.endswith(suffix) for suffix in suffixes)


def url_fetch_blocked_reason(url: str) -> str | None:
    """Return a human-readable block reason, or ``None`` if fetch may proceed."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme: {parsed.scheme!r}"

    host = (parsed.hostname or "").lower()
    if not host:
        return "missing hostname"

    if _host_is_private_or_local(host):
        return f"blocked host: {host}"

    if not is_allowed_external_url(url):
        return f"host not allowlisted: {host}"

    return None


def fetch_allowed_url(url: str) -> SafeFetchResult:
    """GET an allowlisted URL with timeout and response size cap."""
    blocked = url_fetch_blocked_reason(url)
    if blocked:
        return SafeFetchResult(ok=False, url=url, error=blocked)

    byte_cap = max_response_bytes()

    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                redirect_blocked = url_fetch_blocked_reason(str(response.url))
                if redirect_blocked:
                    return SafeFetchResult(
                        ok=False,
                        url=url,
                        error=f"redirect blocked: {redirect_blocked}",
                    )

                raw_content_type = response.headers.get("content-type", "")
                content_type = raw_content_type.split(";", 1)[0].strip().lower() or None

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > byte_cap:
                        return SafeFetchResult(
                            ok=False,
                            url=url,
                            error=f"response exceeds {byte_cap} byte cap",
                        )
                    chunks.append(chunk)

                return SafeFetchResult(
                    ok=True,
                    url=url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_disposition=response.headers.get("content-disposition"),
                    body=b"".join(chunks),
                )
    except httpx.TimeoutException:
        return SafeFetchResult(ok=False, url=url, error="request timed out")
    except httpx.RequestError as exc:
        return SafeFetchResult(ok=False, url=url, error=str(exc))


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def fetch_url_text(url: str) -> str:
    """Best-effort text from an allowlisted URL (PDF or HTML). Login walls return ``""``."""
    text, _error = fetch_url_text_with_error(url)
    return text


def fetch_url_text_with_error(url: str) -> tuple[str, str | None]:
    """Like ``fetch_url_text`` but also returns a fetch/parse error message when empty."""
    attachment = fetch_url_attachment_with_error(url)
    return attachment.text, attachment.error


def fetch_url_attachment_with_error(url: str) -> UrlAttachmentFetch:
    """Fetch an allowlisted URL and return OCR/text plus filename and page count."""
    fetched = fetch_allowed_url(url)
    filename = _resolve_attachment_filename(
        url,
        fetched.content_disposition if fetched.ok else None,
    )
    if not fetched.ok:
        error = fetched.error or "fetch failed"
        logger.debug("pdf_link_fetch_failed url=%s error=%s", url, error)
        return UrlAttachmentFetch(text="", error=error, filename=filename, pages=0)

    content_type = (fetched.content_type or "").lower()
    body = fetched.body

    if content_type == "application/pdf" or body.startswith(b"%PDF"):
        text, pages = _pdf_bytes_to_text(body)
        if not text.strip():
            return UrlAttachmentFetch(
                text="",
                error="pdf OCR text extraction returned empty",
                filename=filename,
                pages=pages,
            )
        return UrlAttachmentFetch(text=text, error=None, filename=filename, pages=pages)
    if content_type.startswith("image/") or _looks_like_image(body):
        text, pages = _image_bytes_to_text(body, content_type)
        if not text.strip():
            return UrlAttachmentFetch(
                text="",
                error="image OCR text extraction returned empty",
                filename=filename,
                pages=pages,
            )
        return UrlAttachmentFetch(text=text, error=None, filename=filename, pages=pages)
    if content_type in ("text/html", "application/xhtml+xml") or _looks_like_html(body):
        text = _html_bytes_to_text(body)
        if not text.strip():
            return UrlAttachmentFetch(
                text="",
                error="html text extraction returned empty",
                filename=filename,
                pages=0,
            )
        return UrlAttachmentFetch(text=text, error=None, filename=filename, pages=0)
    if content_type.startswith("text/"):
        text = body.decode("utf-8", errors="replace").strip()
        if not text:
            return UrlAttachmentFetch(
                text="",
                error="text response was empty",
                filename=filename,
                pages=0,
            )
        return UrlAttachmentFetch(text=text, error=None, filename=filename, pages=0)
    return UrlAttachmentFetch(
        text="",
        error=f"unsupported content type: {content_type or 'unknown'}",
        filename=filename,
        pages=0,
    )


def _link_follow_ocr_max_pages() -> int | None:
    """Return page cap for link-follow OCR; ``None`` means all pages."""
    cap = int(settings.pdf_link_follow_ocr_max_pages)
    return None if cap <= 0 else cap


def _suffix_for_image(content_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/tiff": ".tif",
        "image/bmp": ".bmp",
    }
    return mapping.get(content_type.lower(), ".png")


def _filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"filename\*=UTF-8''([^;\s]+)", value, re.I)
    if match:
        return unquote(match.group(1))
    match = re.search(r'filename="([^"]+)"', value, re.I)
    if match:
        return match.group(1)
    match = re.search(r"filename=([^;\s]+)", value, re.I)
    if match:
        return match.group(1).strip('"')
    return None


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1]
    return name if name else url


def _resolve_attachment_filename(url: str, content_disposition: str | None) -> str:
    from_header = _filename_from_content_disposition(content_disposition)
    if from_header:
        return from_header
    return _filename_from_url(url)


def _pdf_bytes_to_text(body: bytes) -> tuple[str, int]:
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(body)
            tmp.flush()
            tmp_path = tmp.name
        doc = extract_document_via_ocr(tmp_path, max_pages=_link_follow_ocr_max_pages())
        return doc.full_text(), doc.page_count
    except Exception:
        logger.exception("pdf_link_fetch_ocr_failed")
        return "", 0
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def _image_bytes_to_text(body: bytes, content_type: str) -> tuple[str, int]:
    tmp_path: str | None = None
    try:
        suffix = _suffix_for_image(content_type)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(body)
            tmp.flush()
            tmp_path = tmp.name
        doc = extract_document_via_ocr(tmp_path)
        return doc.full_text(), doc.page_count
    except Exception:
        logger.exception("pdf_link_fetch_image_ocr_failed")
        return "", 0
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def _html_bytes_to_text(body: bytes) -> str:
    html = body.decode("utf-8", errors="replace")
    text = _HTML_TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_html(body: bytes) -> bool:
    sample = body[:512].lstrip().lower()
    return sample.startswith(b"<!doctype html") or sample.startswith(b"<html")


def _looks_like_image(body: bytes) -> bool:
    if body.startswith(b"%PDF"):
        return False
    sample = body[:16]
    return (
        sample.startswith(b"\xff\xd8\xff")
        or sample.startswith(b"\x89PNG\r\n\x1a\n")
        or sample.startswith(b"GIF87a")
        or sample.startswith(b"GIF89a")
        or sample.startswith(b"RIFF")
    )


def _host_is_private_or_local(host: str) -> bool:
    lowered = host.lower().strip()
    if lowered in ("localhost", "localhost.localdomain"):
        return True

    try:
        addr = ipaddress.ip_address(lowered)
    except ValueError:
        return False

    return bool(
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )
