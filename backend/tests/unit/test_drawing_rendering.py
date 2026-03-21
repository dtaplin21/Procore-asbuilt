"""Unit tests for drawing rendering service."""

from __future__ import annotations

import pytest

from services.drawing_rendering import DrawingRenderingService


def test_render_pdf_creates_renditions(db_session, sample_pdf_drawing):
    service = DrawingRenderingService(db_session)
    service.render_drawing_pages(sample_pdf_drawing.id)

    db_session.refresh(sample_pdf_drawing)
    assert sample_pdf_drawing.processing_status == "ready"
    assert sample_pdf_drawing.page_count >= 1
    assert len(sample_pdf_drawing.renditions) >= 1
