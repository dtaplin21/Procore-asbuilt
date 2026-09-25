"""Persist legend grounding hits for master drawings."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.legend_grounding import (
    DocumentAiGroundingProvider,
    GroundingHit,
    PageWord,
    page_words_from_positioned,
    run_grounding_for_legend_entries,
)
from ai.pipelines.legend_icon_extraction import (
    LegendIconEntry,
    extract_legend_icons,
    render_pdf_page_image,
)
from config import document_ai_configured, settings
from models.drawing_legend_grounding_hit import DrawingLegendGroundingHit
from models.drawing_text_element import DrawingTextElement


def grounding_is_available() -> bool:
    return bool(settings.document_ai_grounding_enabled and document_ai_configured())


def page_words_from_text_elements(elements: list[DrawingTextElement]) -> list[PageWord]:
    positioned: list[PositionedWord] = []
    for row in elements:
        raw_bbox = row.bbox_json
        if not isinstance(raw_bbox, dict):
            continue
        bbox_json = cast(dict[str, Any], raw_bbox)
        if not all(k in bbox_json for k in ("x0", "y0", "x1", "y1")):
            continue
        x0 = float(bbox_json["x0"])
        y0 = float(bbox_json["y0"])
        x1 = float(bbox_json["x1"])
        y1 = float(bbox_json["y1"])
        width = max(x1 - x0, 1e-6)
        height = max(y1 - y0, 1e-6)
        positioned.append(
            PositionedWord(
                text=str(row.text),
                bbox=BoundingBox(
                    x=x0,
                    y=y0,
                    width=width,
                    height=height,
                    page_width=1.0,
                    page_height=1.0,
                ),
                page_index=cast(int, row.page) - 1,
                ocr_confidence=float(cast(float, row.ocr_confidence or 0.0)),
                token_source=str(row.source),
            )
        )
    return page_words_from_positioned(positioned)


def delete_grounding_hits_for_page(
    session: Session,
    *,
    master_drawing_id: int,
    page: int,
) -> int:
    deleted = (
        session.query(DrawingLegendGroundingHit)
        .filter(
            DrawingLegendGroundingHit.master_drawing_id == int(master_drawing_id),
            DrawingLegendGroundingHit.page == int(page),
        )
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def persist_grounding_hits(
    session: Session,
    *,
    master_drawing_id: int,
    page: int,
    grounding_run_id: str,
    legend_entries: list[LegendIconEntry],
    hits_by_label: dict[str, list[GroundingHit]],
) -> list[DrawingLegendGroundingHit]:
    rows: list[DrawingLegendGroundingHit] = []
    row_id_by_label = {entry.label_text: entry.row_id for entry in legend_entries}

    for label, hits in hits_by_label.items():
        for hit in hits:
            x0, y0, x1, y1 = hit.page_fractional_bbox
            row = DrawingLegendGroundingHit(
                master_drawing_id=int(master_drawing_id),
                page=int(page),
                grounding_run_id=grounding_run_id,
                legend_row_id=row_id_by_label.get(label),
                legend_label_text=label,
                match_method=hit.match_method,
                provider="document_ai",
                bbox_json={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                confidence=float(hit.confidence),
                meta_json={
                    "raw_model_output": hit.raw_model_output,
                },
            )
            session.add(row)
            rows.append(row)

    session.flush()
    return rows


def run_and_persist_legend_grounding(
    session: Session,
    *,
    pdf_path: str,
    master_drawing_id: int,
    page: int,
    legend_bbox_fractional: tuple[float, float, float, float],
    elements: list[DrawingTextElement],
    output_dir: str,
    replace_existing: bool = True,
    provider: DocumentAiGroundingProvider | None = None,
) -> tuple[str, dict[str, list[GroundingHit]], list[DrawingLegendGroundingHit]]:
    if not grounding_is_available():
        raise RuntimeError(
            "Legend grounding requires DOCUMENT_AI_GROUNDING_ENABLED=true and Document AI config",
        )

    entries = extract_legend_icons(
        pdf_path,
        page=page,
        legend_bbox_fractional=legend_bbox_fractional,
        output_dir=output_dir,
        elements=elements,
        prefer_indexed=True,
    )
    if not entries:
        raise ValueError("No legend icon entries to ground")

    full_image = render_pdf_page_image(pdf_path, page=page)
    page_words = page_words_from_text_elements(elements)
    grounding_provider = provider or DocumentAiGroundingProvider()
    hits_by_label = run_grounding_for_legend_entries(
        full_page_image=full_image,
        entries=entries,
        provider=grounding_provider,
        full_page_words=page_words,
    )

    run_id = str(uuid.uuid4())
    if replace_existing:
        delete_grounding_hits_for_page(
            session,
            master_drawing_id=master_drawing_id,
            page=page,
        )

    persisted = persist_grounding_hits(
        session,
        master_drawing_id=master_drawing_id,
        page=page,
        grounding_run_id=run_id,
        legend_entries=entries,
        hits_by_label=hits_by_label,
    )
    session.commit()
    return run_id, hits_by_label, persisted


def list_grounding_hits(
    session: Session,
    *,
    master_drawing_id: int,
    page: int | None = None,
) -> list[DrawingLegendGroundingHit]:
    query = session.query(DrawingLegendGroundingHit).filter(
        DrawingLegendGroundingHit.master_drawing_id == int(master_drawing_id),
    )
    if page is not None:
        query = query.filter(DrawingLegendGroundingHit.page == int(page))
    return query.order_by(
        DrawingLegendGroundingHit.page.asc(),
        DrawingLegendGroundingHit.legend_row_id.asc(),
        DrawingLegendGroundingHit.id.asc(),
    ).all()


def grounding_hits_to_json(rows: list[DrawingLegendGroundingHit]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        bbox = row.bbox_json if isinstance(row.bbox_json, dict) else {}
        out.append(
            {
                "id": cast(int, row.id),
                "page": cast(int, row.page),
                "grounding_run_id": cast(str, row.grounding_run_id),
                "legend_row_id": row.legend_row_id,
                "legend_label_text": cast(str, row.legend_label_text),
                "match_method": cast(str, row.match_method),
                "provider": cast(str, row.provider),
                "confidence": float(cast(float, row.confidence)),
                "bbox_json": bbox,
                "meta_json": row.meta_json,
            }
        )
    return out
