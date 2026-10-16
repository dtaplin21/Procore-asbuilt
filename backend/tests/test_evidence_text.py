"""Tests for evidence text helpers."""

from __future__ import annotations

from types import SimpleNamespace

from services.evidence_text import build_location_reasoning_excerpt


def test_reasoning_excerpt_prefers_stations_over_header() -> None:
    full = (
        "https://app.procore.com/projects/1348/submittals/123\n\n"
        "Generic cover sheet text with no location.\n\n"
        "SAN. STA. 10+00 through 10+90.95 on sheet C4.20 install plan.\n\n"
        "N=2131764.84 E=6051541.82 at SSMH."
    )
    excerpt = build_location_reasoning_excerpt(full, max_chars=4000)
    assert "10+90" in excerpt
    assert "2131764" in excerpt or "6051541" in excerpt
    assert excerpt.index("10+90") < 200 or "Location-relevant" in excerpt


def test_reasoning_excerpt_includes_linked_attachment_previews() -> None:
    attachment = SimpleNamespace(
        filename="U1.C4.20 Sanitary Sewer Install.pdf",
        text_preview="STA 10+00 to 10+90.95 trench run",
    )
    excerpt = build_location_reasoning_excerpt(
        "cover",
        linked_attachments=[attachment],
        max_chars=2000,
    )
    assert "C4.20" in excerpt
    assert "10+90" in excerpt
