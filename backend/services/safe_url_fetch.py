"""Allowlisted HTTP(S) fetch with SSRF guards for PDF link enrichment.

Network and security rules live here — not in the AI pipeline module.
Allowed hosts come from ``config.pdf_link_follow_allowed_host_suffixes()``.
"""

from __future__ import annotations

import ipaddress
import re
import tempfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ai.pipelines.document_text_extraction import extract_document
from config import pdf_link_follow_allowed_host_suffixes

FETCH_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass(frozen=True)
class SafeFetchResult:
    ok: bool
    url: str
    status_code: int | None = None
    content_type: str | None = None
    body: bytes = b""
    error: str | None = None


def is_allowed_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    suffixes = pdf_link_follow_allowed_host_suffixes()
    return any(host == suffix or host.endswith(suffix) for suffix in suffixes)


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
                    if total > MAX_RESPONSE_BYTES:
                        return SafeFetchResult(
                            ok=False,
                            url=url,
                            error=f"response exceeds {MAX_RESPONSE_BYTES} byte cap",
                        )
                    chunks.append(chunk)

                return SafeFetchResult(
                    ok=True,
                    url=url,
                    status_code=response.status_code,
                    content_type=content_type,
                    body=b"".join(chunks),
                )
    except httpx.TimeoutException:
        return SafeFetchResult(ok=False, url=url, error="request timed out")
    except httpx.RequestError as exc:
        return SafeFetchResult(ok=False, url=url, error=str(exc))


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def fetch_url_text(url: str) -> str:
    """Best-effort text from an allowlisted URL (PDF or HTML). Login walls return ``""``."""
    fetched = fetch_allowed_url(url)
    if not fetched.ok:
        return ""

    content_type = (fetched.content_type or "").lower()
    body = fetched.body

    if content_type == "application/pdf" or body.startswith(b"%PDF"):
        return _pdf_bytes_to_text(body)
    if content_type in ("text/html", "application/xhtml+xml") or _looks_like_html(body):
        return _html_bytes_to_text(body)
    if content_type.startswith("text/"):
        return body.decode("utf-8", errors="replace").strip()
    return ""


def _pdf_bytes_to_text(body: bytes) -> str:
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(body)
            tmp.flush()
            tmp_path = tmp.name
        return extract_document(tmp_path).full_text()
    except Exception:
        return ""
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
