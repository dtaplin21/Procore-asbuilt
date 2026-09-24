"""Tests for legend swatch template extraction (Step 2b)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import fitz

from ai.pipelines.legend_line_row_builder import LegendLineRow, cluster_legend_line_rows
from ai.pipelines.legend_line_swatch import (
    LegendLineTemplate,
    build_legend_line_templates,
    classify_chains_with_templates,
    extract_swatch_template,
    legend_line_templates_to_meta,
)
from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleSignature,
    PdfVectorChain,
    extract_pdf_vector_chains,
)
from models.drawing_text_element import DrawingTextElement
from scripts.seed_legend_reference import seed
from services.legend_lookup import match_line_type_by_name


def _write_legend_swatch_pdf(path: Path) -> tuple[float, float, float, float]:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    # Swatch in left legend column (~x 0.04–0.10 fractional).
    page.draw_line((32, 48), (72, 48), width=0.72, color=(0, 0, 0))
    page.draw_line((88, 48), (104, 48), width=0.72, color=(0, 0, 0))
    doc.save(str(path))
    doc.close()
    # Display-space Y is flipped vs PDF user Y (see pdf_display_space).
    return (0.03, 0.88, 0.15, 0.95)


def test_extract_swatch_template_from_bbox(tmp_path: Path) -> None:
    pdf_path = tmp_path / "legend.pdf"
    swatch_bbox = _write_legend_swatch_pdf(pdf_path)

    style = extract_swatch_template(pdf_path, swatch_bbox)

    assert style is not None
    assert style.segment_count >= 1


def test_match_line_type_by_name_after_cluster(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    elements = [
        DrawingTextElement(
            master_drawing_id=1,
            page=1,
            text="SANITARY",
            text_normalized="sanitary",
            bbox_json={"x0": 0.08, "y0": 0.30, "x1": 0.14, "y1": 0.32},
            ocr_confidence=0.9,
            source="tesseract",
        ),
        DrawingTextElement(
            master_drawing_id=1,
            page=1,
            text="SEWER",
            text_normalized="sewer",
            bbox_json={"x0": 0.15, "y0": 0.301, "x1": 0.19, "y1": 0.321},
            ocr_confidence=0.9,
            source="tesseract",
        ),
    ]
    rows = cluster_legend_line_rows(elements)
    assert rows
    row: LegendLineRow = rows[0]

    matched = match_line_type_by_name(
        db_session,
        row.text,
        project_id=project_id,
    )
    assert matched is not None
    assert "SANITARY" in str(matched.line_type_name).upper()


def test_build_legend_line_templates_links_swatch_and_db(db_session, project, tmp_path: Path) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)
    pdf_path = tmp_path / "legend.pdf"
    swatch_bbox = _write_legend_swatch_pdf(pdf_path)

    rows = [
        LegendLineRow(
            text="Sanitary Sewer Main",
            label_bbox=(0.08, 0.30, 0.22, 0.32),
            swatch_bbox=swatch_bbox,
        )
    ]

    templates = build_legend_line_templates(
        db_session,
        pdf_path,
        rows,
        project_id=project_id,
    )

    assert len(templates) == 1
    assert templates[0].abbreviation_code == "SS"
    assert templates[0].style.segment_count >= 1


def test_classify_chains_with_templates(db_session, project, tmp_path: Path) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)
    pdf_path = tmp_path / "legend.pdf"
    swatch_bbox = _write_legend_swatch_pdf(pdf_path)
    plan_chains = extract_pdf_vector_chains(pdf_path)
    assert plan_chains

    style = extract_swatch_template(pdf_path, swatch_bbox)
    assert style is not None
    template = LegendLineTemplate(
        legend_line_type_id=1,
        line_type_name="Sanitary Sewer Main",
        abbreviation_code="SS",
        style=style,
    )

    classified = classify_chains_with_templates(plan_chains[:1], [template])

    assert classified[0][1] == "Sanitary Sewer Main"
    assert classified[0][2] == 1


def test_legend_line_templates_to_meta() -> None:
    style = LineStyleSignature(
        stroke_width_bucket=0.72,
        mean_segment_len_frac=0.01,
        mean_gap_len_frac=0.002,
        segment_count=2,
        kind_guess="dashed",
    )
    meta = legend_line_templates_to_meta(
        [
            LegendLineTemplate(
                legend_line_type_id=5,
                line_type_name="Water Main",
                abbreviation_code="W",
                style=style,
            )
        ]
    )
    assert meta[0]["abbreviation_code"] == "W"
    assert meta[0]["style"]["kind_guess"] == "dashed"
