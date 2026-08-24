"""Tests for Procore document_downloader URL resolution."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.procore_attachment_fetch import (
    parse_procore_document_url,
    resolve_procore_attachment_download_url,
)


def test_parse_procore_document_url_extracts_attachment_and_submittal_ids() -> None:
    url = (
        "https://app.procore.com/2727475/project/submittal_log_approvers/document_downloader"
        "?attachment_id=6001321764&item_id=177539970&item_type=SubmittalLogApprover"
        "&project_id=2727475&source=coversheet&submittal_log_id=69397739"
    )

    parsed = parse_procore_document_url(url)

    assert parsed is not None
    assert parsed["attachment_id"] == "6001321764"
    assert parsed["submittal_log_id"] == "69397739"
    assert parsed["procore_project_id"] == "2727475"


def test_resolve_procore_attachment_download_url_uses_submittal_attachments() -> None:
    url = (
        "https://app.procore.com/2727475/project/submittal_log_approvers/document_downloader"
        "?attachment_id=6001321764&project_id=2727475&submittal_log_id=69397739"
    )
    db = MagicMock()
    db.get.side_effect = lambda model, pk: {
        2: SimpleNamespace(id=2, company_id=10, procore_project_id="2727475"),
        10: SimpleNamespace(id=10, procore_company_id="9871"),
    }.get(pk)

    conn = SimpleNamespace(
        company_id=10,
        procore_user_id="42",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        token_type="Bearer",
        scope=None,
    )

    with (
        patch(
            "services.procore_attachment_fetch._active_connection_for_company",
            return_value=conn,
        ),
        patch(
            "services.procore_attachment_fetch._lookup_attachment_download_url",
            return_value="https://storage.procore.com/files/install.pdf?sig=abc",
        ) as lookup_mock,
    ):
        resolved = resolve_procore_attachment_download_url(url, db=db, project_id=2)

    assert resolved == "https://storage.procore.com/files/install.pdf?sig=abc"
    lookup_mock.assert_called_once()
    assert lookup_mock.call_args.kwargs["attachment_id"] == "6001321764"
