"""Legend graphic swatch templates from PDF vectors + DB line types (Step 2b/3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ai.pipelines.legend_line_typing import (
    ChainTyping,
    LegendTemplate,
    SwatchStyle,
    build_templates,
    classify_chains,
    extract_swatch_style,
)
from ai.pipelines.legend_line_row_builder import LegendLineRow
from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleKind,
    LineStyleSignature,
    PdfVectorChain,
    extract_pdf_vector_segments,
)
from services.legend_lookup import line_type_rows_for_project
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SwatchStyleForMatch:
    """Width + color used for family classification; signature for audit meta."""

    stroke_width_bucket: float
    color: tuple[int, int, int] | None
    kind_guess: LineStyleKind
    signature: LineStyleSignature


@dataclass(frozen=True)
class LegendLineTemplate:
    legend_line_type_id: int
    line_type_name: str
    abbreviation_code: str | None
    style: SwatchStyleForMatch
    row_index: int | None = None


def _signature_from_swatch(sw: SwatchStyle) -> LineStyleSignature:
    kind: LineStyleKind = "dashed" if sw.kind_guess == "stub_gap" else "solid"
    seg_count = 2 if sw.kind_guess == "stub_gap" else 1
    return LineStyleSignature(
        stroke_width_bucket=sw.stroke_width_bucket,
        mean_segment_len_frac=sw.stub_len,
        mean_gap_len_frac=sw.gap_len,
        segment_count=seg_count,
        kind_guess=kind,
    )


def _style_for_match(sw: SwatchStyle) -> SwatchStyleForMatch:
    sig = _signature_from_swatch(sw)
    return SwatchStyleForMatch(
        stroke_width_bucket=sw.stroke_width_bucket,
        color=sw.color,
        kind_guess=sig.kind_guess,
        signature=sig,
    )


def extract_swatch_template(
    pdf_path: str | Path,
    swatch_bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
) -> LineStyleSignature | None:
    """Legacy API: returns ``LineStyleSignature`` only (no color)."""
    style = extract_swatch_style_for_bbox(pdf_path, swatch_bbox, page=page)
    return style.signature if style is not None else None


def extract_swatch_style_for_bbox(
    pdf_path: str | Path,
    swatch_bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
) -> SwatchStyleForMatch | None:
    segments = extract_pdf_vector_segments(pdf_path, page=page)
    sw = extract_swatch_style(segments, swatch_bbox)
    if sw is None:
        return None
    return _style_for_match(sw)


def _template_from_legend(t: LegendTemplate, style: SwatchStyleForMatch) -> LegendLineTemplate:
    return LegendLineTemplate(
        legend_line_type_id=t.legend_line_type_id,
        line_type_name=t.line_type_name,
        abbreviation_code=t.abbreviation_code,
        style=style,
        row_index=t.row_index,
    )


def build_legend_line_templates(
    session: Session,
    pdf_path: str | Path,
    rows: list[LegendLineRow],
    *,
    project_id: int | None,
    page: int = 1,
) -> list[LegendLineTemplate]:
    templates, _diag = build_legend_line_templates_with_diagnostics(
        session,
        pdf_path,
        rows,
        project_id=project_id,
        page=page,
    )
    return templates


def build_legend_line_templates_with_diagnostics(
    session: Session,
    pdf_path: str | Path,
    rows: list[LegendLineRow],
    *,
    project_id: int | None,
    page: int = 1,
) -> tuple[list[LegendLineTemplate], list[dict[str, Any]]]:
    line_types = line_type_rows_for_project(session, project_id=project_id)
    segments = extract_pdf_vector_segments(pdf_path, page=page)

    def extract_style(bbox: tuple[float, float, float, float]) -> SwatchStyleForMatch | None:
        sw = extract_swatch_style(segments, bbox)
        if sw is None:
            return None
        return _style_for_match(sw)

    raw_templates, diag = build_templates(rows, line_types, extract_style)
    templates: list[LegendLineTemplate] = []
    for rt in raw_templates:
        style = cast(SwatchStyleForMatch, rt.style)
        templates.append(_template_from_legend(rt, style))
    return templates, diag


def classify_chains_with_templates(
    chains: list[PdfVectorChain],
    templates: list[LegendLineTemplate],
) -> list[tuple[PdfVectorChain, str | None, int | None]]:
    """Returns (chain, line_type_name, legend_line_type_id) per plan chain."""
    legend_tpls = [
        LegendTemplate(
            t.legend_line_type_id,
            t.line_type_name,
            t.abbreviation_code,
            t.style,
            t.row_index,
        )
        for t in templates
    ]
    typings = classify_chains(chains, legend_tpls)
    out: list[tuple[PdfVectorChain, str | None, int | None]] = []
    for chain, ty in zip(chains, typings):
        if ty.status == "typed":
            out.append((chain, ty.line_type_name, ty.legend_line_type_id))
        else:
            out.append((chain, None, None))
    return out


def classify_chain_typings(
    chains: list[PdfVectorChain],
    templates: list[LegendLineTemplate],
) -> list[ChainTyping]:
    legend_tpls = [
        LegendTemplate(
            t.legend_line_type_id,
            t.line_type_name,
            t.abbreviation_code,
            t.style,
            t.row_index,
        )
        for t in templates
    ]
    return classify_chains(chains, legend_tpls)


def legend_line_templates_to_meta(templates: list[LegendLineTemplate]) -> list[dict[str, Any]]:
    """JSON-serializable template list for ``SheetEntityGraph.meta``."""
    return [
        {
            "legend_line_type_id": t.legend_line_type_id,
            "line_type_name": t.line_type_name,
            "abbreviation_code": t.abbreviation_code,
            "row_index": t.row_index,
            "style": {
                "stroke_width_bucket": t.style.signature.stroke_width_bucket,
                "mean_segment_len_frac": t.style.signature.mean_segment_len_frac,
                "mean_gap_len_frac": t.style.signature.mean_gap_len_frac,
                "kind_guess": t.style.signature.kind_guess,
                "color_rgb": list(t.style.color) if t.style.color else None,
            },
        }
        for t in templates
    ]
