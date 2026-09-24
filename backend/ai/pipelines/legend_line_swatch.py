"""Legend graphic swatch templates from PDF vectors + DB line types (Step 2b)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleSignature,
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
