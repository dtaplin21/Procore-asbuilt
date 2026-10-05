"""Bootstrap master ↔ aux registration before inspection placement."""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.registration_from_survey import (
    compute_registration_for_linked_drawings,
    registration_transform_to_meta,
)
from ai.pipelines.station_label_composition import extract_station_control_points_from_elements
from ai.pipelines.survey_point_extractor import extract_survey_points_from_elements
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import EvidenceRecord
from services.survey_point_storage import persist_station_control_points

logger = logging.getLogger(__name__)


def _registration_in_meta(meta: dict[str, Any]) -> bool:
    raw = meta.get("registration_transform")
    return isinstance(raw, dict) and raw.get("scale_x") is not None


def _stations_on_aux_drawings(session: Session, linked_drawing_ids: list[int]) -> set[str]:
    stations: set[str] = set()
    if not linked_drawing_ids:
        return stations
    rows = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id.in_(linked_drawing_ids))
        .all()
    )
    for row in rows:
        station = cast(str | None, row.station)
        if station and station.strip():
            stations.add(station.strip().upper())
    return stations


def bootstrap_master_station_controls(
    session: Session,
    *,
    master_drawing_id: int,
    linked_drawing_ids: list[int],
    target_stations: set[str] | None = None,
) -> int:
    """Seed master station control points when OCR split labels or only aux has N/E."""
    if target_stations is None:
        target_stations = _stations_on_aux_drawings(session, linked_drawing_ids)
    if not target_stations:
        return 0

    elements = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == master_drawing_id)
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    if not elements:
        return 0

    from models.models import Drawing

    drawing = session.get(Drawing, master_drawing_id)
    page_meta_json = cast(list[dict[str, Any]] | None, getattr(drawing, "page_meta_json", None)) or []
    scale_json = cast(dict[str, Any] | None, getattr(drawing, "scale_json", None))

    records = extract_station_control_points_from_elements(
        elements,
        page_meta_json=page_meta_json,
        scale_source="match_registration_bootstrap",
    )
    # Also try full N/E pairing (no-op when master lacks coordinates).
    records.extend(
        extract_survey_points_from_elements(
            elements,
            scale_json=scale_json,
            page_meta_json=page_meta_json,
            scale_source="match_registration_bootstrap",
        )
    )

    filtered = [
        record
        for record in records
        if record.station and record.station.strip().upper() in target_stations
    ]
    if not filtered:
        return 0

    count = persist_station_control_points(
        session,
        master_drawing_id,
        filtered,
        source="match_registration_bootstrap",
    )
    if count:
        logger.info(
            "master_station_controls_bootstrapped",
            extra={
                "master_drawing_id": master_drawing_id,
                "control_point_count": count,
                "target_stations": sorted(target_stations)[:12],
            },
        )
    return count


def ensure_evidence_registration_for_match(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    linked_drawing_ids: list[int],
) -> bool:
    """Compute and persist registration_transform on evidence when control points allow."""
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is None:
        return False

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    if _registration_in_meta(meta):
        return True

    meta_stations: set[str] = set()
    for key in ("station_from", "station_to"):
        raw = meta.get(key)
        if isinstance(raw, str) and raw.strip():
            meta_stations.add(raw.strip().upper())
    raw_points = meta.get("survey_points")
    if isinstance(raw_points, list):
        for item in raw_points:
            if isinstance(item, dict):
                station = item.get("station")
                if isinstance(station, str) and station.strip():
                    meta_stations.add(station.strip().upper())

    target_stations = meta_stations | _stations_on_aux_drawings(session, linked_drawing_ids)
    bootstrap_master_station_controls(
        session,
        master_drawing_id=master_drawing_id,
        linked_drawing_ids=linked_drawing_ids,
        target_stations=target_stations,
    )

    transform, control_point_count, aux_drawing_id = compute_registration_for_linked_drawings(
        session,
        linked_drawing_ids=linked_drawing_ids,
        master_drawing_id=master_drawing_id,
    )
    if transform is None or control_point_count < 1:
        return False

    meta["registration_transform"] = registration_transform_to_meta(
        transform,
        control_point_count=control_point_count,
        aux_drawing_id=aux_drawing_id,
    )
    evidence.meta = meta  # type: ignore[assignment]
    session.flush()
    logger.info(
        "evidence_registration_ready",
        extra={
            "evidence_id": evidence_id,
            "master_drawing_id": master_drawing_id,
            "control_point_count": control_point_count,
            "aux_drawing_id": aux_drawing_id,
        },
    )
    return True
