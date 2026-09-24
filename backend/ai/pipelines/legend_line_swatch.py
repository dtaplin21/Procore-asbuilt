"""Legend graphic swatch templates from PDF vectors + DB line types (Step 2b)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ai.pipelines.line_style_match import signature_distance
from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleSignature,
    PdfVectorChain,
    extract_pdf_vector_segments,
    segments_to_chains,
)
from ai.pipelines.legend_line_row_builder import LegendLineRow
from models.legend_reference import DrawingLegendLineType
from services.legend_lookup import match_line_type_by_name
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class LegendLineTemplate:
    legend_line_type_id: int
    line_type_name: str
    abbreviation_code: str | None
    style: LineStyleSignature


def extract_swatch_template(
    pdf_path: str | Path,
    swatch_bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
) -> LineStyleSignature | None:
    x0, y0, x1, y1 = swatch_bbox
    segments = extract_pdf_vector_segments(pdf_path, page=page)
    inside = [
        s
        for s in segments
        if x0 <= (s.x0 + s.x1) / 2.0 <= x1 and y0 <= (s.y0 + s.y1) / 2.0 <= y1
    ]
    if not inside:
        return None
    chains = segments_to_chains(
        inside,
        min_polyline_length_frac=0.0001,
    )
    if not chains:
        return None
    chains.sort(
        key=lambda c: -sum(
            ((c.points[i + 1][0] - c.points[i][0]) ** 2 + (c.points[i + 1][1] - c.points[i][1]) ** 2)
            ** 0.5
            for i in range(len(c.points) - 1)
        )
    )
    return chains[0].style


def build_legend_line_templates(
    session: Session,
    pdf_path: str | Path,
    rows: list[LegendLineRow],
    *,
    project_id: int | None,
    page: int = 1,
) -> list[LegendLineTemplate]:
    templates: list[LegendLineTemplate] = []
    for row in rows:
        style = extract_swatch_template(pdf_path, row.swatch_bbox, page=page)
        if style is None:
            continue
        db_row = match_line_type_by_name(session, row.text, project_id=project_id)
        if db_row is None:
            continue
        templates.append(
            LegendLineTemplate(
                legend_line_type_id=cast(int, db_row.id),
                line_type_name=str(cast(str, db_row.line_type_name)),
                abbreviation_code=_abbreviation_code(db_row),
                style=style,
            )
        )
    return templates


def _abbreviation_code(row: DrawingLegendLineType) -> str | None:
    code = row.abbreviation_code
    if code is None:
        return None
    return str(code)


def classify_chains_with_templates(
    chains: list[PdfVectorChain],
    templates: list[LegendLineTemplate],
) -> list[tuple[PdfVectorChain, str | None, int | None]]:
    """Returns (chain, line_type_name, legend_line_type_id) per plan chain."""
    out: list[tuple[PdfVectorChain, str | None, int | None]] = []
    for chain in chains:
        if not templates:
            out.append((chain, None, None))
            continue
        best = min(templates, key=lambda t: signature_distance(chain.style, t.style))
        out.append((chain, best.line_type_name, best.legend_line_type_id))
    return out


def legend_line_templates_to_meta(templates: list[LegendLineTemplate]) -> list[dict[str, Any]]:
    """JSON-serializable template list for ``SheetEntityGraph.meta``."""
    return [
        {
            "legend_line_type_id": t.legend_line_type_id,
            "line_type_name": t.line_type_name,
            "abbreviation_code": t.abbreviation_code,
            "style": {
                "stroke_width_bucket": t.style.stroke_width_bucket,
                "mean_segment_len_frac": t.style.mean_segment_len_frac,
                "mean_gap_len_frac": t.style.mean_gap_len_frac,
                "kind_guess": t.style.kind_guess,
            },
        }
        for t in templates
    ]
