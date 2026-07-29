"""Unit tests for allowlisted external URL fetch guards."""

from __future__ import annotations

from services.safe_url_fetch import is_allowed_external_url, url_fetch_blocked_reason


def test_procore_app_url_is_allowed() -> None:
    url = "https://app.procore.com/projects/123/locations/456"

    assert is_allowed_external_url(url) is True
    assert url_fetch_blocked_reason(url) is None


def test_localhost_is_rejected() -> None:
    url = "http://127.0.0.1/secret"

    assert is_allowed_external_url(url) is False
    reason = url_fetch_blocked_reason(url)
    assert reason is not None
    assert "127.0.0.1" in reason


def test_file_scheme_is_rejected() -> None:
    url = "file:///etc/passwd"

    assert is_allowed_external_url(url) is False
    reason = url_fetch_blocked_reason(url)
    assert reason is not None
    assert "file" in reason
