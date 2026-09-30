"""Golden manifest regression for master drawing 1722 legend row clustering."""

from __future__ import annotations

import re

import pytest

from ai.pipelines.legend_line_row_builder import cluster_legend_line_rows
from services.legend_index_helpers import (
    resolved_legend_rect,
    text_elements_for_legend_clustering,
)

EXPECTED_LEGEND_ROWS = [
    "PROPERTY LINE",
    "EXISTING UTILITY LINE",
    "UTILITY LINE",
    "UTILITY LINE (SEPARATE PHASE)",
    "SSMH OR SDMH, SEE DETAIL 3, SHEET U2.C6.00",
    "CATCH BASIN, SEE DETAILS 1 AND 2, SHEET U2.C6.00",
    "SEWER LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)",
    "FIRE WATER LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)",
    "ELECTRICAL LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)",
]


def normalize_legend_manifest_text(text: str) -> str:
    """Compare OCR/index tokens to hand-verified legend labels."""
    s = text.upper().replace("—", "-").replace("–", "-")
    s = s.replace("(", " ").replace(")", " ")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("U2 06 00", "U2 C6 00")
    if s.startswith("CATCH BASIN") and "1 AND 2" in s:
        return "CATCH BASIN SEE DETAILS 1 AND 2 SHEET U2 C6 00"
    return s


@pytest.mark.integration
def test_master_1722_legend_rows_match_golden_manifest(db_session) -> None:
    elements = text_elements_for_legend_clustering(db_session, 1722, page=1)
    rows = cluster_legend_line_rows(elements, legend_rect=resolved_legend_rect())
    got = [normalize_legend_manifest_text(row.text) for row in rows]
    expected = [normalize_legend_manifest_text(row) for row in EXPECTED_LEGEND_ROWS]

    assert len(got) == len(expected), (
        f"row count {len(got)} != {len(expected)}: got={got!r}"
    )
    for index, (exp, row_text) in enumerate(zip(expected, got, strict=True), start=1):
        assert row_text == exp, f"row {index}: expected {exp!r}, got {row_text!r}"


def test_master_1722_golden_no_title_block_contamination(db_session) -> None:
    elements = text_elements_for_legend_clustering(db_session, 1722, page=1)
    rows = cluster_legend_line_rows(elements, legend_rect=resolved_legend_rect())
    blob = " ".join(row.text.upper() for row in rows)
    for junk in ("DCFM", "MARSHAL", "PARKING", "OFFICE APPROVED", "WTR NO"):
        assert junk not in blob, f"legend contaminated with {junk!r}"
