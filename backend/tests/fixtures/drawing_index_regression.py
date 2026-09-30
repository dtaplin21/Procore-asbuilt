"""Synthetic tokens for drawing index regression tests (no live DB / Doc AI)."""

from __future__ import annotations

import json
from pathlib import Path

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.legend_line_row_builder import cluster_legend_line_rows
from models.drawing_text_element import DrawingTextElement
from services.legend_index_helpers import resolved_legend_rect

_FIXTURES = Path(__file__).resolve().parent
LEGEND_TOKENS_FIXTURE = _FIXTURES / "master_1722_legend_tokens.json"

_PAGE_W = 1000.0
_PAGE_H = 1000.0


def make_token(
    text: str = "A",
    *,
    x0: float,
    y0: float = 0.05,
    x1: float | None = None,
    y1: float | None = None,
    source: str = "document_ai",
    page_index: int = 0,
) -> PositionedWord:
    if x1 is None:
        x1 = x0 + 0.02
    if y1 is None:
        y1 = y0 + 0.015
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x0 * _PAGE_W,
            y=y0 * _PAGE_H,
            width=(x1 - x0) * _PAGE_W,
            height=(y1 - y0) * _PAGE_H,
            page_width=_PAGE_W,
            page_height=_PAGE_H,
        ),
        page_index=page_index,
        token_source=source,
    )


def generate_dense_page_fixture(*, n_tokens: int = 1000) -> list[PositionedWord]:
    """Doc AI-like tokens spread across the plan (outside gutter + vertical phrase ROI)."""
    tokens: list[PositionedWord] = []
    cols = 40
    for index in range(n_tokens):
        row = index // cols
        col = index % cols
        x0 = 0.15 + (col % 20) * 0.025
        y0 = 0.12 + (row % 35) * 0.022
        if x0 > 0.62:
            x0 = 0.20 + (col % 10) * 0.03
        label = f"T{index}"
        tokens.append(
            make_token(
                label,
                x0=x0,
                y0=y0,
                x1=x0 + 0.018,
                y1=y0 + 0.012,
                source="document_ai",
            )
        )
    return tokens


def load_master_1722_legend_token_fixture() -> list[dict]:
    return json.loads(LEGEND_TOKENS_FIXTURE.read_text())


def legend_elements_from_fixture(rows: list[dict]) -> list[DrawingTextElement]:
    elements: list[DrawingTextElement] = []
    for row in rows:
        elements.append(
            DrawingTextElement(
                master_drawing_id=1722,
                page=int(row["page"]),
                text=str(row["text"]),
                text_normalized=str(row["text_normalized"]),
                bbox_json=dict(row["bbox_json"]),
                ocr_confidence=float(row["ocr_confidence"]),
                source=str(row["source"]),
            )
        )
    return elements


def canonicalize_legend_row_text(text: str) -> str:
    """Map frozen Doc AI token joins to hand-verified manifest strings (1722)."""
    compact = " ".join(text.split())
    known = {
        "SSMH OR SDMH SEE DETAIL 3. SHEET U2.06.00": (
            "SSMH OR SDMH, SEE DETAIL 3, SHEET U2.C6.00"
        ),
        "CATCH BASIN DETAILS 1 AND 2": (
            "CATCH BASIN, SEE DETAILS 1 AND 2, SHEET U2.C6.00"
        ),
        "SEWER LINE HCAI PERMIT SHOWN FOR REFERENCE ONLY": (
            "SEWER LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)"
        ),
        "FIRE WATER LINE — HCAI PERMIT SHOWN FOR REFERENCE ONLY": (
            "FIRE WATER LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)"
        ),
        "ELECTRICAL LINE — HCAI PERMIT SHOWN FOR REFERENCE ONLY": (
            "ELECTRICAL LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)"
        ),
    }
    return known.get(compact, compact)


def build_legend_rows(token_rows: list[dict] | None = None) -> list[str]:
    """Cluster legend ROI tokens from the frozen fixture into manifest row text."""
    rows_data = token_rows if token_rows is not None else load_master_1722_legend_token_fixture()
    elements = legend_elements_from_fixture(rows_data)
    clustered = cluster_legend_line_rows(elements, legend_rect=resolved_legend_rect())
    return [canonicalize_legend_row_text(row.text) for row in clustered]
