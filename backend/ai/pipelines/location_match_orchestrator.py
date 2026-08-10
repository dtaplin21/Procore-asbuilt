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
from ai.pipelines.coordinate_frame import normalize_to_true_north
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.drawing_location_resolver import (
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
from services.file_storage import get_file_path
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD, MatchStatus
from services.match_candidate_scope import MatchScope, build_match_scope
from services.region_index_loader import build_region_index
from services.survey_point_storage import persist_survey_points

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
        candidate: MethodCandidate,
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
    if not isinstance(label_bbox, dict):
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
        scale_source="lazy_match",
    )
    if not records:
        return []

    try:
        persist_survey_points(
            session,
            drawing_id,
            records,
            source="lazy_match",
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
        for record in records
        if isinstance(record.label_bbox_json, dict)
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
) -> list[MethodCandidate]:
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

    bbox = _rotate_bbox_for_drawing_page(
        session,
        scoped.drawing_id,
        scoped.page,
        _bbox_from_json(scoped.label_bbox_json),
    )
    return [
        MethodCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=match.confidence,
            bbox_fractional=bbox,
            page=scoped.page,
            source_drawing_id=scoped.drawing_id,
            notes=(
                f"Survey coordinate match at {match.distance_ft:.2f} ft "
                f"on drawing {scoped.drawing_id}."
            ),
        )
    ]


def _station_lookup_candidates(
    session: Session,
    *,
    evidence_points: Sequence[SurveyPointRecord],
    scoped_points: Sequence[_ScopedSurveyPoint],
    master_drawing_id: int,
) -> list[MethodCandidate]:
    evidence_stations: set[str] = {
        station
        for point in evidence_points
        if (station := _normalize_station(point.station))
    }
    if not evidence_stations:
        return []

    candidates: list[MethodCandidate] = []
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
            MethodCandidate(
                method=ResolutionMethod.STATION_LOOKUP,
                confidence=STATION_MATCH_CONFIDENCE,
                bbox_fractional=bbox,
                page=preferred.page,
                source_drawing_id=preferred.drawing_id,
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
) -> list[MethodCandidate]:
    candidates: list[MethodCandidate] = []
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

        candidates.append(
            MethodCandidate(
                method=ResolutionMethod.REFERENCE_LOOKUP,
                confidence=min(best_score, 0.94),
                bbox_fractional=best_tile.bbox_normalized,
                page=best_tile.page,
                region_id=best_tile.region_id,
                source_drawing_id=int(drawing_id),
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
) -> MethodCandidate | None:
    storage_key = cast(str | None, evidence.storage_key)
    if not storage_key:
        return None

    file_path = get_file_path(storage_key)
    if not file_path.exists():
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

    return MethodCandidate(
        method=resolved.method,
        confidence=resolved.confidence_score,
        bbox_fractional=resolved.bbox_fractional,
        page=1,
        region_id=region_id,
        source_drawing_id=master_drawing_id,
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
) -> MethodCandidate | None:
    storage_key = cast(str | None, evidence.storage_key)
    if not storage_key:
        return None

    file_path = get_file_path(storage_key)
    if not file_path.exists():
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

    return MethodCandidate(
        method=ResolutionMethod.CONTOUR_MATCH,
        confidence=contour.confidence,
        bbox_fractional=contour.bbox_fractional,
        page=page,
        source_drawing_id=master_drawing_id,
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
    storage_key = cast(str | None, evidence.storage_key)
    if storage_key:
        file_path = get_file_path(storage_key)
        if file_path.exists():
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

    scope: MatchScope = build_match_scope(
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
    project_id = cast(int | None, evidence.project_id)
    registration_transform = _load_registration_transform(evidence)

    candidates: list[MethodCandidate] = []

    candidates.extend(
        _coordinate_lookup_candidates(
            session,
            evidence_points=evidence_points,
            scoped_points=scoped_points,
            master_drawing_id=master_drawing_id,
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

    winner = select_best_location_match(candidates)
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
        return LocationMatchResult.from_candidate(master_drawing_id, contour)

    return LocationMatchResult.unresolved(master_drawing_id)
