"""Resolve Procore app URLs (document_downloader) to signed storage download URLs."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from html import unescape
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from config import procore_api_base_url, procore_token_url, settings
from models.models import Company, Project, ProcoreConnection

logger = logging.getLogger(__name__)

_DOCUMENT_PATH_RE = re.compile(
    r"/(?P<procore_project_id>\d+)/project/[^/]+/(?:document_downloader|document_viewer)",
    re.I,
)


def parse_procore_document_url(url: str) -> dict[str, str] | None:
    """Parse attachment/submittal ids from Procore document viewer/downloader URLs."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if "procore.com" not in host or "app." not in host:
        return None
    if not _DOCUMENT_PATH_RE.search(parsed.path):
        return None

    query = parse_qs(parsed.query)
    attachment_id = _first_query_value(query, "attachment_id")
    if not attachment_id:
        return None

    path_match = _DOCUMENT_PATH_RE.search(parsed.path)
    procore_project_id = (
        _first_query_value(query, "project_id")
        or (path_match.group("procore_project_id") if path_match else None)
    )
    if not procore_project_id:
        return None

    return {
        "attachment_id": attachment_id,
        "procore_project_id": procore_project_id,
        "submittal_log_id": _first_query_value(query, "submittal_log_id") or "",
        "item_id": _first_query_value(query, "item_id") or "",
        "item_type": _first_query_value(query, "item_type") or "",
    }


def resolve_procore_attachment_download_url(
    url: str,
    *,
    db: Session,
    project_id: int,
) -> str | None:
    """Return a signed storage URL for a Procore document_downloader link when OAuth is available."""
    parsed = parse_procore_document_url(url)
    if parsed is None:
        return None

    project = db.get(Project, project_id)
    if project is None:
        return None

    company = db.get(Company, cast(int, project.company_id))
    if company is None:
        return None

    conn = _active_connection_for_company(db, cast(int, project.company_id))
    if conn is None:
        logger.debug(
            "procore_attachment_resolve_skipped",
            extra={"reason": "no_active_connection", "project_id": project_id},
        )
        return None

    procore_company_id = cast(str | None, company.procore_company_id)
    procore_project_id = cast(str, project.procore_project_id or parsed["procore_project_id"])

    try:
        access_token = _ensure_access_token(db, conn)
    except Exception:
        logger.exception(
            "procore_attachment_token_refresh_failed",
            extra={"project_id": project_id},
        )
        return None

    download_url = _lookup_attachment_download_url(
        access_token=access_token,
        procore_company_id=procore_company_id,
        procore_project_id=procore_project_id,
        attachment_id=parsed["attachment_id"],
        submittal_log_id=parsed.get("submittal_log_id") or None,
    )
    if download_url:
        logger.info(
            "procore_attachment_resolved",
            extra={
                "project_id": project_id,
                "attachment_id": parsed["attachment_id"],
                "resolved_host": urlparse(download_url).hostname,
            },
        )
    return download_url


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _active_connection_for_company(
    db: Session,
    company_id: int,
) -> ProcoreConnection | None:
    return (
        db.query(ProcoreConnection)
        .filter(
            ProcoreConnection.company_id == company_id,
            ProcoreConnection.is_active.is_(True),
            ProcoreConnection.revoked_at.is_(None),
        )
        .order_by(ProcoreConnection.updated_at.desc())
        .first()
    )


def _ensure_access_token(db: Session, conn: ProcoreConnection) -> str:
    expires_at = cast(datetime, conn.token_expires_at)
    if datetime.utcnow() < expires_at - timedelta(minutes=5):
        return cast(str, conn.access_token)

    refresh_token = cast(str, conn.refresh_token)
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            procore_token_url(),
            data={
                "client_id": settings.procore_client_id,
                "client_secret": settings.procore_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = response.json()

    expires_in = int(token_data.get("expires_in", 3600))
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    conn.access_token = str(token_data["access_token"])
    conn.refresh_token = str(token_data.get("refresh_token", refresh_token))
    conn.token_expires_at = expires_at
    conn.token_type = str(token_data.get("token_type", conn.token_type or "Bearer"))
    db.add(conn)
    db.flush()
    return cast(str, conn.access_token)


def _lookup_attachment_download_url(
    *,
    access_token: str,
    procore_company_id: str | None,
    procore_project_id: str,
    attachment_id: str,
    submittal_log_id: str | None,
) -> str | None:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if procore_company_id:
        headers["Procore-Company-Id"] = procore_company_id

    base = f"{procore_api_base_url()}/rest/v1.0"

    if submittal_log_id:
        url = _url_from_submittal_attachments(
            base_url=base,
            headers=headers,
            procore_project_id=procore_project_id,
            submittal_log_id=submittal_log_id,
            attachment_id=attachment_id,
        )
        if url:
            return url

    return _url_from_file_endpoint(
        base_url=base,
        headers=headers,
        procore_project_id=procore_project_id,
        attachment_id=attachment_id,
    )


def _url_from_submittal_attachments(
    *,
    base_url: str,
    headers: dict[str, str],
    procore_project_id: str,
    submittal_log_id: str,
    attachment_id: str,
) -> str | None:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{base_url}/submittals/{submittal_log_id}/attachments",
            params={"project_id": procore_project_id},
            headers=headers,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()

    for item in _ensure_list(payload):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id is not None and str(item_id) == str(attachment_id):
            return _pick_download_url(item)
        nested_file = item.get("file")
        if isinstance(nested_file, dict):
            nested_id = nested_file.get("id")
            if nested_id is not None and str(nested_id) == str(attachment_id):
                return _pick_download_url(nested_file) or _pick_download_url(item)
    return None


def _url_from_file_endpoint(
    *,
    base_url: str,
    headers: dict[str, str],
    procore_project_id: str,
    attachment_id: str,
) -> str | None:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{base_url}/files/{attachment_id}",
            params={"project_id": procore_project_id},
            headers=headers,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()

    if isinstance(payload, dict):
        return _pick_download_url(payload)
    return None


def _pick_download_url(record: dict[str, Any]) -> str | None:
    for key in ("url", "download_url", "file_url", "s3_source"):
        value = record.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return unescape(value.strip())
    return None


def _ensure_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "attachments", "files"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return nested
    return []
