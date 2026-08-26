"""Unified location-match orchestrator for inspection evidence on master drawings."""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import (
    CandidateTile,
    bbox_on_page,
    compute_tile_match_score,
    find_candidate_tiles_from_clues,
)
from ai.pipelines.fractional_coords import bbox_intersects_page
from ai.pipelines.coordinate_frame import normalize_to_true_north
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.drawing_location_resolver import (
    MasterRegion,
    RegistrationTransform,
    ResolutionMethod,
    resolve_document_location,
)
from ai.pipelines.evidence_kind_classifier import (
    EvidenceKind,
    classify_evidence_kind,
    contour_matching_enabled,
    has_linked_install_sheet,
)
from ai.pipelines.resolution_vocab import RESOLUTION_VOCAB_CATEGORIES
from ai.pipelines.landmark_extractor import LandmarkRecord
from ai.pipelines.landmark_matcher import run_landmark_matcher
from ai.pipelines.positioned_term_extractor import extract_positioned_terms
from ai.pipelines.survey_point_extractor import (
    SurveyPointRecord,
    extract_stations_from_text,
    extract_survey_points_from_elements,
    is_placed_survey_label_bbox,
)
from ai.pipelines.survey_point_matcher import (
    COORD_MATCH_TOLERANCE_FT,
    SurveyPointMatch,
    euclidean_survey_distance_ft,
    match_survey_points,
)
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.drawing_landmark import DrawingLandmark
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, EvidenceRecord
from services.evidence_text import build_full_evidence_text
from services.file_storage import resolve_stored_file_path
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD, MatchStatus
from services.match_candidate_scope import MatchScope, build_match_scope
from services.region_index_loader import build_region_index
from services.survey_point_storage import persist_survey_points
from observability.location_match_logging import log_inspection_match_candidates

logger = logging.getLogger(__name__)

SCORE_TIE_EPSILON = 0.01

METHOD_TIEBREAK_PRIORITY: tuple[ResolutionMethod, ...] = (
    ResolutionMethod.COORDINATE_LOOKUP,
    ResolutionMethod.STATION_LOOKUP,
    ResolutionMethod.REFERENCE_LOOKUP,
    ResolutionMethod.ALIGNMENT,
    ResolutionMethod.CONTOUR_MATCH,
)

STATION_MATCH_CONFIDENCE = 0.88
_STATION_NORMALIZE_RE = re.compile(r"\s+")
_REGION_CLUSTER_LIMIT = 3
_SHEET_REF_TOKEN_RE = re.compile(
    r"^(?:[A-Z]{1,3}-?\d{2,4}[A-Z]?|[A-Z]\d+\.[A-Z]\d+\.\d{2,4}|[A-Z]\d+\.\d{2,4})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MethodCandidate:
    method: ResolutionMethod
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    page: int = 1
    region_id: int | None = None
    source_drawing_id: int | None = None
    notes: str = ""


@dataclass(frozen=True)
class LocationMatchCandidate:
    method: ResolutionMethod
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    page: int
    region_id: int | None = None
    source_drawing_id: int | None = None
    supporting_clues: tuple[str, ...] = ()
    contradicting_signals: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class LocationMatchResult:
    master_drawing_id: int
    method: ResolutionMethod
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    page: int
    region_id: int | None = None
    notes: str = ""

    @classmethod
    def unresolved(
        cls,
        master_drawing_id: int,
        *,
        notes: str = "No location match found.",
    ) -> LocationMatchResult:
        return cls(
            master_drawing_id=master_drawing_id,
            method=ResolutionMethod.UNRESOLVED,
            confidence=0.0,
            bbox_fractional=None,
            page=1,
            region_id=None,
            notes=notes,
        )

    @classmethod
    def from_candidate(
        cls,
        master_drawing_id: int,
        candidate: MethodCandidate | LocationMatchCandidate,
    ) -> LocationMatchResult:
        return cls(
            master_drawing_id=master_drawing_id,
            method=candidate.method,
            confidence=candidate.confidence,
            bbox_fractional=candidate.bbox_fractional,
            page=candidate.page,
            region_id=candidate.region_id,
            notes=candidate.notes,
        )


def method_candidate_from_location(
    candidate: LocationMatchCandidate,
) -> MethodCandidate:
    return MethodCandidate(
        method=candidate.method,
        confidence=candidate.confidence,
        bbox_fractional=candidate.bbox_fractional,
        page=candidate.page,
        region_id=candidate.region_id,
        source_drawing_id=candidate.source_drawing_id,
        notes=candidate.notes,
    )


def _is_sheet_ref_token(value: str) -> bool:
    cleaned = value.strip().upper().replace(" ", "")
    if not cleaned:
        return False
    return bool(_SHEET_REF_TOKEN_RE.match(cleaned))


def _clue_display_value(clue: DocumentClue) -> str:
    return str(getattr(clue, "clue_value", None) or getattr(clue, "value", "") or "").strip()


def _non_sheet_supporting_clues(clues: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        clue
        for clue in clues
        if not _is_sheet_ref_token(clue.split(":", 1)[-1])
    )


def _filter_off_page_candidates(
    candidates: Sequence[LocationMatchCandidate],
) -> list[LocationMatchCandidate]:
    """Drop candidates whose bbox does not overlap the drawable page."""
    kept: list[LocationMatchCandidate] = []
    for candidate in candidates:
        bbox = candidate.bbox_fractional
        if bbox is None or bbox_intersects_page(bbox):
            kept.append(candidate)
    return kept


def _filter_sheet_only_candidates(
    candidates: Sequence[LocationMatchCandidate],
) -> list[LocationMatchCandidate]:
    """Drop candidates whose only supporting signals are sheet-number tokens."""
    kept: list[LocationMatchCandidate] = []
    for candidate in candidates:
        if not candidate.supporting_clues:
            kept.append(candidate)
            continue
        if _non_sheet_supporting_clues(candidate.supporting_clues):
            kept.append(candidate)
    return kept


def _region_clue_hits(
    region: MasterRegion,
    clues: Sequence[DocumentClue],
) -> tuple[str, ...]:
    location_labels = {label.lower() for label in region.location_labels}
    inspection_types = {tag.lower() for tag in region.inspection_types}
    hits: list[str] = []
    for clue in clues:
        if getattr(clue, "location_relevant", True) is False:
            continue
        value = _clue_display_value(clue)
        if not value or _is_sheet_ref_token(value):
            continue
        lower = value.lower()
        if any(lower in label or label in lower for label in location_labels):
            hits.append(f"location:{value}")
        if any(lower in tag or tag in lower for tag in inspection_types):
            hits.append(f"inspection_type:{value}")
    return tuple(dict.fromkeys(hits))


def _region_cluster_candidates(
    session: Session,
    *,
    master_drawing_id: int,
    clues: Sequence[DocumentClue],
    page: int,
    limit: int = _REGION_CLUSTER_LIMIT,
) -> list[LocationMatchCandidate]:
    regions = build_region_index(session, master_drawing_id).regions
    scored: list[tuple[float, MasterRegion, tuple[str, ...]]] = []
    for region in regions:
        hits = _region_clue_hits(region, clues)
        if not hits:
            continue
        score = min(0.45 + 0.12 * len(hits), 0.88)
        scored.append((score, region, hits))
    scored.sort(key=lambda item: (-item[0], item[1].region_id))

    candidates: list[LocationMatchCandidate] = []
    for score, region, hits in scored[:limit]:
        bbox = region.bbox_on_master.to_fractional()
        region_id = int(region.region_id) if region.region_id.isdigit() else None
        candidates.append(
            LocationMatchCandidate(
                method=ResolutionMethod.REFERENCE_LOOKUP,
                confidence=score,
                bbox_fractional=bbox,
                page=page,
                region_id=region_id,
                source_drawing_id=master_drawing_id,
                supporting_clues=hits,
                notes=f"Region cluster overlap ({', '.join(hits)}).",
            )
        )
    return candidates


def _clue_hits_for_tile(
    tile: CandidateTile,
    clues: Sequence[DocumentClue],
) -> tuple[str, ...]:
    haystack = tile.text.upper()
    hits: list[str] = []
    for clue in clues:
        value = _clue_display_value(clue)
        if not value or _is_sheet_ref_token(value):
            continue
        if value.upper() in haystack:
            hits.append(f"clue:{value}")
    return tuple(dict.fromkeys(hits))


@dataclass(frozen=True)
class _ScopedSurveyPoint:
    drawing_id: int
    page: int
    northing: float
    easting: float
    station: str | None
    structure_label: str | None
    label_bbox_json: dict[str, float]
    ocr_confidence: float


def _method_priority(method: ResolutionMethod) -> int:
    try:
        return METHOD_TIEBREAK_PRIORITY.index(method)
    except ValueError:
        return len(METHOD_TIEBREAK_PRIORITY)


def select_best_location_match(
    candidates: Sequence[MethodCandidate],
) -> MethodCandidate | None:
    """Pick the highest-confidence candidate; tie-break by method priority within epsilon."""
    actionable = [
        candidate
        for candidate in candidates
        if candidate.confidence > 0 and candidate.bbox_fractional is not None
    ]
    if not actionable:
        return None

    best_confidence = max(candidate.confidence for candidate in actionable)
    tied = [
        candidate
        for candidate in actionable
        if candidate.confidence >= best_confidence - SCORE_TIE_EPSILON
    ]
    return min(
        tied,
        key=lambda candidate: (_method_priority(candidate.method), -candidate.confidence),
    )


def match_status_from_result(result: LocationMatchResult) -> MatchStatus:
    if result.method == ResolutionMethod.UNRESOLVED:
        return "no_match"
    if result.method == ResolutionMethod.CONTOUR_MATCH:
        return "needs_review"
    if result.confidence >= MATCH_SCORE_THRESHOLD:
        return "matched"
    return "needs_review"


def _normalize_station(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _STATION_NORMALIZE_RE.sub("", value.strip().upper())
    return normalized or None


def _bbox_from_json(bbox_json: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        float(bbox_json["x0"]),
        float(bbox_json["y0"]),
        float(bbox_json["x1"]),
        float(bbox_json["y1"]),
    )


def _rotate_bbox_for_drawing_page(
    session: Session,
    drawing_id: int,
    page: int,
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    drawing = session.get(Drawing, drawing_id)
    page_meta_json = cast(list[dict[str, Any]] | None, getattr(drawing, "page_meta_json", None))
    if not isinstance(page_meta_json, list):
        return bbox
    for entry in page_meta_json:
        if int(entry.get("page", 1)) != page:
            continue
        rotation = entry.get("true_north_rotation_deg")
        if rotation is not None:
            return normalize_to_true_north(bbox, float(rotation))
    return bbox


def _meta_survey_points(evidence: EvidenceRecord) -> list[SurveyPointRecord]:
    meta = cast(dict[str, Any] | None, evidence.meta)
    raw_points = meta.get("survey_points") if isinstance(meta, dict) else None
    if not isinstance(raw_points, list):
        return []

    points: list[SurveyPointRecord] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        try:
            label_bbox = item["label_bbox_json"]
            if not isinstance(label_bbox, dict):
                continue
            points.append(
                SurveyPointRecord(
                    page=int(item.get("page", 1)),
                    northing=float(item["northing"]),
                    easting=float(item["easting"]),
                    station=cast(str | None, item.get("station")),
                    structure_label=cast(str | None, item.get("structure_label")),
                    label_bbox_json=label_bbox,
                    northing_bbox_json=cast(dict[str, float] | None, item.get("northing_bbox_json")),
                    easting_bbox_json=cast(dict[str, float] | None, item.get("easting_bbox_json")),
                    ocr_confidence=float(item.get("ocr_confidence", 1.0)),
                    meta_json=cast(dict[str, Any], item.get("meta_json") or {}),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return points


def _scoped_point_from_row(row: DrawingSurveyPoint) -> _ScopedSurveyPoint | None:
    label_bbox = cast(dict[str, float] | None, row.label_bbox_json)
    meta_json = cast(dict[str, Any] | None, row.meta_json)
    source = cast(str | None, row.source)
    if not is_placed_survey_label_bbox(
        label_bbox,
        source=source,
        meta_json=meta_json,
    ):
        return None
    return _ScopedSurveyPoint(
        drawing_id=cast(int, row.drawing_id),
        page=cast(int, row.page),
        northing=cast(float, row.northing),
        easting=cast(float, row.easting),
        station=cast(str | None, row.station),
        structure_label=cast(str | None, row.structure_label),
        label_bbox_json=label_bbox,
        ocr_confidence=cast(float, row.ocr_confidence),
    )


def _lazy_extract_drawing_survey_points(
    session: Session,
    drawing_id: int,
) -> list[_ScopedSurveyPoint]:
    """Extract N/E points from indexed OCR text when drawing_survey_points is empty."""
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return []

    elements: list[DrawingTextElement] = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    if not elements:
        return []

    page_meta_json = cast(list[dict[str, Any]] | None, drawing.page_meta_json) or []
    scale_json = cast(dict[str, Any] | None, drawing.scale_json)
    records = extract_survey_points_from_elements(
        elements,
        scale_json=scale_json,
        page_meta_json=page_meta_json,
        scale_source="match_investigation",
    )
    placed_records = [
        record
        for record in records
        if is_placed_survey_label_bbox(
            record.label_bbox_json,
            source="match_investigation",
            meta_json=record.meta_json,
        )
    ]
    if not placed_records:
        return []

    try:
        persist_survey_points(
            session,
            drawing_id,
            placed_records,
            source="match_investigation",
        )
    except Exception:
        logger.exception(
            "lazy_survey_point_persist_failed",
            extra={"drawing_id": drawing_id},
        )

    return [
        _ScopedSurveyPoint(
            drawing_id=drawing_id,
            page=record.page,
            northing=record.northing,
            easting=record.easting,
            station=record.station,
            structure_label=record.structure_label,
            label_bbox_json=record.label_bbox_json,
            ocr_confidence=record.ocr_confidence,
        )
        for record in placed_records
    ]


def _load_scoped_survey_points(
    session: Session,
    drawing_ids: Sequence[int],
) -> list[_ScopedSurveyPoint]:
    if not drawing_ids:
        return []

    rows: list[DrawingSurveyPoint] = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id.in_(list(drawing_ids)))
        .order_by(DrawingSurveyPoint.drawing_id.asc(), DrawingSurveyPoint.id.asc())
        .all()
    )
    points: list[_ScopedSurveyPoint] = []
    drawings_with_rows: set[int] = set()
    for row in rows:
        scoped = _scoped_point_from_row(row)
        if scoped is None:
            continue
        drawings_with_rows.add(scoped.drawing_id)
        points.append(scoped)

    for drawing_id in drawing_ids:
        if int(drawing_id) in drawings_with_rows:
            continue
        points.extend(_lazy_extract_drawing_survey_points(session, int(drawing_id)))
    return points


def _enrich_evidence_stations(
    points: Sequence[SurveyPointRecord],
    *,
    clues: Sequence[DocumentClue],
    evidence_text: str,
) -> list[SurveyPointRecord]:
    """Fill missing station fields from clues / evidence text (plain-text fallback path)."""
    if not points:
        return []

    clue_text = " ".join(
        str(getattr(clue, "clue_value", None) or getattr(clue, "value", "") or "")
        for clue in clues
    )
    stations = extract_stations_from_text(clue_text) or extract_stations_from_text(
        evidence_text
    )
    if not stations:
        return list(points)

    enriched: list[SurveyPointRecord] = []
    for index, point in enumerate(points):
        if point.station:
            enriched.append(point)
            continue
        station = stations[min(index, len(stations) - 1)]
        enriched.append(
            SurveyPointRecord(
                page=point.page,
                northing=point.northing,
                easting=point.easting,
                station=station,
                structure_label=point.structure_label,
                label_bbox_json=point.label_bbox_json,
                northing_bbox_json=point.northing_bbox_json,
                easting_bbox_json=point.easting_bbox_json,
                ocr_confidence=point.ocr_confidence,
                meta_json={**point.meta_json, "station_enriched_from_text": True},
            )
        )
    return enriched


def _project_aux_bbox_to_master(
    session: Session,
    *,
    aux_point: _ScopedSurveyPoint,
    master_drawing_id: int,
    registration_transform: RegistrationTransform | None,
) -> tuple[float, float, float, float] | None:
    """Map an auxiliary drawing survey bbox onto master fractional space."""
    if registration_transform is None:
        return None
    try:
        aux_bbox = _bbox_from_json(aux_point.label_bbox_json)
    except (KeyError, TypeError, ValueError):
        return None

    projected = registration_transform.apply(*aux_bbox)
    return _rotate_bbox_for_drawing_page(
        session,
        master_drawing_id,
        aux_point.page,
        projected,
    )


def _prefer_master_scoped_point(
    match: SurveyPointMatch,
    *,
    master_drawing_id: int,
    scoped_points: Sequence[_ScopedSurveyPoint],
) -> _ScopedSurveyPoint | None:
    master_point = cast(_ScopedSurveyPoint, match.master)
    if master_point.drawing_id == master_drawing_id:
        return master_point

    for candidate in scoped_points:
        if candidate.drawing_id != master_drawing_id:
            continue
        if (
            euclidean_survey_distance_ft(match.evidence, candidate)
            <= COORD_MATCH_TOLERANCE_FT
        ):
            return candidate
    return master_point


def _coordinate_lookup_candidates(
    session: Session,
    *,
    evidence_points: Sequence[SurveyPointRecord],
    scoped_points: Sequence[_ScopedSurveyPoint],
    master_drawing_id: int,
    registration_transform: RegistrationTransform | None = None,
) -> list[LocationMatchCandidate]:
    if not evidence_points or not scoped_points:
        return []

    match = match_survey_points(evidence_points, scoped_points)
    if match is None:
        return []

    scoped = _prefer_master_scoped_point(
        match,
        master_drawing_id=master_drawing_id,
        scoped_points=scoped_points,
    )
    if scoped is None:
        return []

    supporting = (
        f"coordinate:n={match.evidence.northing},e={match.evidence.easting}",
        f"survey_distance:{match.distance_ft:.2f}ft",
    )

    if scoped.drawing_id == master_drawing_id:
        bbox = _rotate_bbox_for_drawing_page(
            session,
            scoped.drawing_id,
            scoped.page,
            _bbox_from_json(scoped.label_bbox_json),
        )
        notes = (
            f"Survey coordinate match at {match.distance_ft:.2f} ft "
            f"on master drawing {scoped.drawing_id}."
        )
        contradicting: tuple[str, ...] = ()
    else:
        projected_bbox = _project_aux_bbox_to_master(
            session,
            aux_point=scoped,
            master_drawing_id=master_drawing_id,
            registration_transform=registration_transform,
        )
        if projected_bbox is not None:
            bbox = projected_bbox
            notes = (
                f"Survey coordinate match at {match.distance_ft:.2f} ft; "
                f"projected from auxiliary drawing {scoped.drawing_id} to master."
            )
            contradicting = ()
        else:
            bbox = _rotate_bbox_for_drawing_page(
                session,
                scoped.drawing_id,
                scoped.page,
                _bbox_from_json(scoped.label_bbox_json),
            )
            notes = (
                "aux_coords_unprojected: survey match on auxiliary drawing "
                f"{scoped.drawing_id} at {match.distance_ft:.2f} ft without master projection."
            )
            contradicting = ("aux_coords_unprojected",)

    return [
        LocationMatchCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=match.confidence,
            bbox_fractional=bbox,
            page=scoped.page,
            source_drawing_id=scoped.drawing_id,
            supporting_clues=supporting,
            contradicting_signals=contradicting,
            notes=notes,
        )
    ]


def _station_lookup_candidates(
    session: Session,
    *,
    evidence_points: Sequence[SurveyPointRecord],
    scoped_points: Sequence[_ScopedSurveyPoint],
    master_drawing_id: int,
) -> list[LocationMatchCandidate]:
    evidence_stations: set[str] = {
        station
        for point in evidence_points
        if (station := _normalize_station(point.station))
    }
    if not evidence_stations:
        return []

    candidates: list[LocationMatchCandidate] = []
    for station in sorted(evidence_stations):
        master_matches = [
            point
            for point in scoped_points
            if _normalize_station(point.station) == station
        ]
        if not master_matches:
            continue

        preferred = next(
            (point for point in master_matches if point.drawing_id == master_drawing_id),
            master_matches[0],
        )
        bbox = _rotate_bbox_for_drawing_page(
            session,
            preferred.drawing_id,
            preferred.page,
            _bbox_from_json(preferred.label_bbox_json),
        )
        candidates.append(
            LocationMatchCandidate(
                method=ResolutionMethod.STATION_LOOKUP,
                confidence=STATION_MATCH_CONFIDENCE,
                bbox_fractional=bbox,
                page=preferred.page,
                source_drawing_id=preferred.drawing_id,
                supporting_clues=(f"station:{station}",),
                notes=f"Station match for {station!r} on drawing {preferred.drawing_id}.",
            )
        )
    return candidates


def _clue_tile_candidates(
    session: Session,
    *,
    drawing_ids: Sequence[int],
    page: int,
    clues: Sequence[DocumentClue],
    project_id: int | None,
) -> list[LocationMatchCandidate]:
    candidates: list[LocationMatchCandidate] = []
    for drawing_id in drawing_ids:
        tiles = find_candidate_tiles_from_clues(
            session=session,
            drawing_id=drawing_id,
            page=page,
            clues=clues,
            limit=20,
            project_id=project_id,
        )
        if not tiles:
            continue

        best_score = 0.0
        best_tile: CandidateTile | None = None
        for tile in tiles:
            score = compute_tile_match_score(
                tile,
                clues,
                session=session,
                project_id=project_id,
            )
            if score > best_score:
                best_score = score
                best_tile = tile

        if (
            best_tile is None
            or best_score <= 0
            or best_tile.bbox_normalized is None
            or not bbox_on_page(best_tile.bbox_normalized)
        ):
            continue

        supporting = _clue_hits_for_tile(best_tile, clues)
        if not supporting:
            continue

        candidates.append(
            LocationMatchCandidate(
                method=ResolutionMethod.REFERENCE_LOOKUP,
                confidence=min(best_score, 0.94),
                bbox_fractional=best_tile.bbox_normalized,
                page=best_tile.page,
                region_id=best_tile.region_id,
                source_drawing_id=int(drawing_id),
                supporting_clues=supporting,
                notes=f"Clue tile match on drawing {drawing_id}.",
            )
        )
    return candidates


def _reference_lookup_candidate(
    session: Session,
    *,
    evidence: EvidenceRecord,
    master_drawing_id: int,
    registration_transform: RegistrationTransform | None,
) -> LocationMatchCandidate | None:
    storage_key = cast(str | None, evidence.storage_key)
    file_path = resolve_stored_file_path(storage_key)
    if file_path is None:
        return None

    document = extract_document(file_path)
    positioned_terms = extract_positioned_terms(
        document,
        categories=RESOLUTION_VOCAB_CATEGORIES,
    )
    region_index = build_region_index(session, master_drawing_id).regions
    resolved = resolve_document_location(
        positioned_terms,
        str(master_drawing_id),
        region_index,
        registration_transform=registration_transform,
    )
    if resolved.bbox_fractional is None or resolved.confidence_score <= 0:
        return None

    region_id: int | None = None
    if resolved.matched_region is not None and resolved.matched_region.region_id.isdigit():
        region_id = int(resolved.matched_region.region_id)

    supporting: list[str] = []
    for term in positioned_terms:
        category = getattr(term.term, "category", None)
        canonical = str(getattr(term.term, "canonical", "") or "").strip()
        if not canonical or _is_sheet_ref_token(canonical):
            continue
        if category is not None:
            supporting.append(f"{category.value}:{canonical}")
        else:
            supporting.append(f"term:{canonical}")

    return LocationMatchCandidate(
        method=resolved.method,
        confidence=resolved.confidence_score,
        bbox_fractional=resolved.bbox_fractional,
        page=1,
        region_id=region_id,
        source_drawing_id=master_drawing_id,
        supporting_clues=tuple(dict.fromkeys(supporting)),
        notes=resolved.notes,
    )


def _load_master_landmarks(
    session: Session,
    master_drawing_id: int,
    page: int,
) -> list[LandmarkRecord]:
    rows: list[DrawingLandmark] = (
        session.query(DrawingLandmark)
        .filter(
            DrawingLandmark.drawing_id == master_drawing_id,
            DrawingLandmark.page == page,
        )
        .order_by(DrawingLandmark.id.asc())
        .all()
    )
    landmarks: list[LandmarkRecord] = []
    for row in rows:
        bbox_json = cast(dict[str, float] | None, row.bbox_json)
        hu_moments = cast(list[float] | None, row.hu_moments_json)
        if not isinstance(bbox_json, dict) or not isinstance(hu_moments, list):
            continue
        landmarks.append(
            LandmarkRecord(
                page=cast(int, row.page),
                landmark_type=cast(Any, row.landmark_type),
                bbox_json=bbox_json,
                hu_moments_json=[float(value) for value in hu_moments],
                ocr_confidence=cast(float, row.ocr_confidence),
                meta_json=cast(dict[str, Any], row.meta_json or {}),
            )
        )
    return landmarks


def _evidence_rendition_png(
    file_path: Path,
    *,
    page: int,
) -> tuple[str, dict[str, Any]]:
    """Render one evidence page to a temporary PNG for contour matching."""
    import fitz

    suffix = file_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        return str(file_path), {"page": page, "width_pt": None, "height_pt": None}

    doc = fitz.open(str(file_path))
    try:
        page_index = max(page - 1, 0)
        if page_index >= doc.page_count:
            page_index = 0
        pdf_page = doc.load_page(page_index)
        pixmap = pdf_page.get_pixmap(dpi=200, alpha=False)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_file.write(pixmap.tobytes("png"))
        temp_file.close()
        return temp_file.name, {
            "page": page_index + 1,
            "width_pt": float(pdf_page.rect.width),
            "height_pt": float(pdf_page.rect.height),
        }
    finally:
        doc.close()


def _contour_match_candidate(
    session: Session,
    *,
    evidence: EvidenceRecord,
    master_drawing_id: int,
    page: int,
) -> LocationMatchCandidate | None:
    storage_key = cast(str | None, evidence.storage_key)
    file_path = resolve_stored_file_path(storage_key)
    if file_path is None:
        return None

    master_landmarks = _load_master_landmarks(session, master_drawing_id, page)
    if not master_landmarks:
        return None

    rendition_path, page_meta = _evidence_rendition_png(file_path, page=page)
    try:
        contour = run_landmark_matcher(
            master_landmarks=master_landmarks,
            evidence_rendition_png=rendition_path,
            evidence_page_meta=page_meta,
        )
    finally:
        if rendition_path != str(file_path):
            Path(rendition_path).unlink(missing_ok=True)

    if contour is None:
        return None

    return LocationMatchCandidate(
        method=ResolutionMethod.CONTOUR_MATCH,
        confidence=contour.confidence,
        bbox_fractional=contour.bbox_fractional,
        page=page,
        source_drawing_id=master_drawing_id,
        supporting_clues=("contour:landmark_match",),
        notes=contour.notes,
    )


def _load_evidence_kind(
    session: Session,
    evidence: EvidenceRecord,
    extraction: DocumentExtraction | None,
) -> EvidenceKind:
    meta = cast(dict[str, Any] | None, evidence.meta)
    if isinstance(meta, dict):
        raw_kind = meta.get("evidence_kind")
        if isinstance(raw_kind, str):
            try:
                return EvidenceKind(raw_kind)
            except ValueError:
                pass

    document_type = str(getattr(extraction, "document_type", "") or "unknown")
    native_words = 0
    file_path = resolve_stored_file_path(cast(str | None, evidence.storage_key))
    if file_path is not None:
        try:
            native_words = sum(
                1
                for word in extract_document(file_path).words
                if word.page_index == 0 and word.text.strip()
            )
        except Exception:
            logger.exception(
                "evidence_kind_native_word_count_failed",
                extra={"evidence_id": evidence.id},
            )

    return classify_evidence_kind(
        document_type,
        has_linked_sheet=has_linked_install_sheet(session, cast(int, evidence.id)),
        native_page1_words=native_words,
    )


def _load_registration_transform(
    evidence: EvidenceRecord,
) -> RegistrationTransform | None:
    meta = cast(dict[str, Any] | None, evidence.meta)
    if not isinstance(meta, dict):
        return None
    raw = meta.get("registration_transform")
    if not isinstance(raw, dict):
        return None
    try:
        return RegistrationTransform(
            scale_x=float(raw["scale_x"]),
            scale_y=float(raw["scale_y"]),
            translate_x=float(raw["translate_x"]),
            translate_y=float(raw["translate_y"]),
            rotation_degrees=float(raw.get("rotation_degrees", 0.0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def project_polyline_to_master(
    points: Sequence[tuple[float, float]],
    registration_transform: RegistrationTransform,
) -> tuple[tuple[float, float], ...]:
    """Project normalized aux polyline vertices onto the master drawing frame."""
    from ai.pipelines.registration_from_survey import (
        project_polyline_to_master as _project_polyline,
    )

    return _project_polyline(points, registration_transform)


def _load_document_extraction(
    session: Session,
    evidence_id: int,
) -> tuple[DocumentExtraction | None, list[DocumentClue]]:
    extraction = (
        session.query(DocumentExtraction)
        .filter_by(file_id=str(evidence_id))
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )
    if extraction is None:
        return None, []

    clues = (
        session.query(DocumentClue)
        .filter_by(document_extraction_id=extraction.id)
        .all()
    )
    return extraction, clues


def generate_all_location_candidates(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    page: int = 1,
) -> list[LocationMatchCandidate]:
    """Run all non-contour matchers and emit provenance-rich candidates."""
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is None:
        return []

    scope = build_match_scope(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )
    _extraction, clues = _load_document_extraction(session, evidence_id)
    drawing_ids = (scope.master_drawing_id, *scope.auxiliary_drawing_ids)
    scoped_points = _load_scoped_survey_points(session, drawing_ids)
    evidence_points = _enrich_evidence_stations(
        _meta_survey_points(evidence),
        clues=clues,
        evidence_text=build_full_evidence_text(evidence),
    )
    project_id = cast(int | None, evidence.project_id)
    registration_transform = _load_registration_transform(evidence)

    candidates: list[LocationMatchCandidate] = []
    candidates.extend(
        _coordinate_lookup_candidates(
            session,
            evidence_points=evidence_points,
            scoped_points=scoped_points,
            master_drawing_id=master_drawing_id,
            registration_transform=registration_transform,
        )
    )
    candidates.extend(
        _station_lookup_candidates(
            session,
            evidence_points=evidence_points,
            scoped_points=scoped_points,
            master_drawing_id=master_drawing_id,
        )
    )
    candidates.extend(
        _clue_tile_candidates(
            session,
            drawing_ids=drawing_ids,
            page=page,
            clues=clues,
            project_id=project_id,
        )
    )
    candidates.extend(
        _region_cluster_candidates(
            session,
            master_drawing_id=master_drawing_id,
            clues=clues,
            page=page,
        )
    )

    reference = _reference_lookup_candidate(
        session,
        evidence=evidence,
        master_drawing_id=master_drawing_id,
        registration_transform=None,
    )
    if reference is not None:
        candidates.append(reference)

    if registration_transform is not None:
        alignment = _reference_lookup_candidate(
            session,
            evidence=evidence,
            master_drawing_id=master_drawing_id,
            registration_transform=registration_transform,
        )
        if alignment is not None and alignment.method == ResolutionMethod.ALIGNMENT:
            candidates.append(alignment)

    return _filter_off_page_candidates(_filter_sheet_only_candidates(candidates))


def _coordinate_projection_log_entries(
    candidates: Sequence[LocationMatchCandidate],
    *,
    master_drawing_id: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.method != ResolutionMethod.COORDINATE_LOOKUP:
            continue
        source_id = candidate.source_drawing_id
        projected = (
            candidate.bbox_fractional is not None
            and source_id is not None
            and source_id != master_drawing_id
            and "projected from auxiliary" in candidate.notes
        )
        entries.append(
            {
                "source_drawing_id": source_id,
                "projected": projected,
                "aux_coords_unprojected": "aux_coords_unprojected" in candidate.notes,
                "has_bbox": candidate.bbox_fractional is not None,
            }
        )
    return entries


def resolve_evidence_location(
    session: Session,
    evidence_id: int,
    master_drawing_id: int,
    page: int = 1,
) -> LocationMatchResult:
    """Run all location matchers and return the best resolved pin on the master drawing."""
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is None:
        return LocationMatchResult.unresolved(
            master_drawing_id,
            notes=f"Evidence {evidence_id} not found.",
        )

    scope = build_match_scope(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )
    extraction, clues = _load_document_extraction(session, evidence_id)
    evidence_kind = _load_evidence_kind(session, evidence, extraction)

    drawing_ids = (scope.master_drawing_id, *scope.auxiliary_drawing_ids)
    scoped_points = _load_scoped_survey_points(session, drawing_ids)
    evidence_points = _enrich_evidence_stations(
        _meta_survey_points(evidence),
        clues=clues,
        evidence_text=build_full_evidence_text(evidence),
    )

    location_candidates = generate_all_location_candidates(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        page=page,
    )
    method_candidates = [
        method_candidate_from_location(candidate)
        for candidate in location_candidates
    ]

    match_detail = {
        "evidence_kind": evidence_kind.value,
        "evidence_point_count": len(evidence_points),
        "scoped_point_count": len(scoped_points),
        "auxiliary_drawing_ids": list(scope.auxiliary_drawing_ids),
        "clue_count": len(clues),
        "coordinate_lookup_skipped": not evidence_points or not scoped_points,
        "has_registration_transform": _load_registration_transform(evidence) is not None,
        "candidate_count": len(location_candidates),
        "coordinate_projections": _coordinate_projection_log_entries(
            location_candidates,
            master_drawing_id=master_drawing_id,
        ),
    }
    log_inspection_match_candidates(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        candidates=method_candidates,
        match_detail=match_detail,
    )

    winner = select_best_location_match(method_candidates)
    if winner is not None:
        return LocationMatchResult.from_candidate(master_drawing_id, winner)

    if not contour_matching_enabled(evidence_kind):
        return LocationMatchResult.unresolved(
            master_drawing_id,
            notes=f"Non-drawing evidence ({evidence_kind.value}); contour fallback skipped.",
        )

    contour = _contour_match_candidate(
        session,
        evidence=evidence,
        master_drawing_id=master_drawing_id,
        page=page,
    )
    if contour is not None:
        contour_method = method_candidate_from_location(contour)
        log_inspection_match_candidates(
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
            candidates=[*method_candidates, contour_method],
            match_detail={**match_detail, "contour_fallback": True},
        )
        return LocationMatchResult.from_candidate(master_drawing_id, contour)

    return LocationMatchResult.unresolved(master_drawing_id)
