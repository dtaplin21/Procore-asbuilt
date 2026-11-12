"""Read-only view of what the master-drawing pipeline stored.

Geometry in the payload is master pixels (display frame, y down). Stored
rows are fractional 0–1 in that same frame; this module multiplies by the
rendition size. Missing layers stay empty and are named in ``warnings``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.positioned_term_extractor import extract_positioned_terms_for_page
from ai.pipelines.station_label_composition import extract_station_control_points_from_elements
from ai.pipelines.survey_point_extractor import extract_stations_from_text
from ai.pipelines.term_extractor import extract_terms
from config import settings
from models.drawing_landmark import DrawingLandmark
from models.drawing_overlay import DrawingOverlay
from models.drawing_region import DrawingRegion
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_symbol import DrawingSymbol
from models.drawing_text_element import DrawingTextElement
from models.inspection_run import InspectionRun
from models.models import Drawing, DrawingRendition, EvidenceRecord, Project
from services.sheet_digitization import load_page_lines

_STATION_VALUE = re.compile(r"^(\d+)\+(\d+(?:\.\d+)?)$")
_SSMH = re.compile(r"\b(SSMH|SMH|MANHOLE|MH-?\d+)\b", re.IGNORECASE)
_COLLINEAR = 0.92


def _frac_box(raw: Any) -> tuple[float, float, float, float] | None:
    if isinstance(raw, dict):
        keys = ("x0", "y0", "x1", "y1")
        if all(k in raw for k in keys):
            return tuple(float(raw[k]) for k in keys)  # type: ignore[return-value]
        if all(k in raw for k in ("x", "y", "width", "height")):
            x = float(raw["x"])
            y = float(raw["y"])
            return x, y, x + float(raw["width"]), y + float(raw["height"])
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return tuple(float(v) for v in raw)  # type: ignore[return-value]
    return None


def _px_box(
    box: tuple[float, float, float, float], width: float, height: float
) -> dict[str, float]:
    x0, y0, x1, y1 = box
    return {
        "x": x0 * width,
        "y": y0 * height,
        "width": max(0.0, (x1 - x0) * width),
        "height": max(0.0, (y1 - y0) * height),
    }


def _px_point(x: float, y: float, width: float, height: float) -> dict[str, float]:
    return {"x": x * width, "y": y * height}


def _center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def _overlaps(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _stamp_station(item: dict[str, Any], station: str) -> None:
    item["isStationLabel"] = True
    item["stationLabel"] = station
    parsed = _parsed_station(station)
    if parsed is not None:
        item["parsedStation"] = parsed


def _parsed_station(label: str) -> float | None:
    match = _STATION_VALUE.fullmatch(label.strip())
    if match is None:
        return None
    return int(match.group(1)) * 100 + float(match.group(2))


def _line_points(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, dict):
        return []
    points = raw.get("points")
    if not isinstance(points, list):
        return []
    out: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            out.append((float(point[0]), float(point[1])))
    return out


def _overlay_polylines(geometry: Any) -> list[list[tuple[float, float]]]:
    if not isinstance(geometry, dict) or geometry.get("type") == "none":
        return []
    points = _line_points(geometry)
    if len(points) >= 2:
        return [points]
    segments = geometry.get("segments")
    if isinstance(segments, list):
        poly: list[tuple[float, float]] = []
        for segment in segments:
            if isinstance(segment, list) and len(segment) >= 2:
                start, end = segment[0], segment[1]
                if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)):
                    poly.append((float(start[0]), float(start[1])))
                    poly.append((float(end[0]), float(end[1])))
        if len(poly) >= 2:
            return [poly]
    box = _frac_box(geometry)
    if box is not None:
        x0, y0, x1, y1 = box
        return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]
    return []


def _region_polygon(region: DrawingRegion) -> list[tuple[float, float]]:
    raw_points = region.polygon_points
    points: list[tuple[float, float]] = []
    if isinstance(raw_points, list):
        for point in raw_points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
            elif isinstance(point, dict) and "x" in point and "y" in point:
                points.append((float(point["x"]), float(point["y"])))
    if len(points) >= 3:
        return points
    box = _frac_box(region.geometry)
    if box is None:
        return []
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _collinearity(points: list[tuple[float, float]]) -> float:
    """1 when the points lie on a line, 0 when they span area."""
    if len(points) < 3:
        return 1.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    sample = points[:12]
    max_area = 0.0
    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            for k in range(j + 1, len(sample)):
                ax, ay = sample[i]
                bx, by = sample[j]
                cx, cy = sample[k]
                area = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2.0
                max_area = max(max_area, area)
    return 1.0 - min(1.0, max_area / (span * span))


def _classify_boxes(
    rows: list[DrawingTextElement],
    width: float,
    height: float,
) -> dict[int, str]:
    """Category per text-element id, from the pipeline's vocabulary matcher."""
    categories: dict[int, str] = {}
    words: list[PositionedWord] = []
    ordered = sorted(
        rows,
        key=lambda row: (
            ((box := _frac_box(row.bbox_json)) or (0, 0, 0, 0))[1],
            (box or (0, 0, 0, 0))[0],
        ),
    )
    for row in ordered:
        box = _frac_box(row.bbox_json)
        text = str(row.text or "").strip()
        if box is None or not text:
            continue
        own = extract_terms(text)
        if own:
            categories[int(row.id)] = own[0].category.value
        x0, y0, x1, y1 = box
        words.append(
            PositionedWord(
                text=text,
                bbox=BoundingBox(
                    x=x0 * width,
                    y=y0 * height,
                    width=max(1.0, (x1 - x0) * width),
                    height=max(1.0, (y1 - y0) * height),
                    page_width=width,
                    page_height=height,
                ),
                page_index=0,
                ocr_confidence=float(row.ocr_confidence or 0.0),
            )
        )
    if not words:
        return categories
    for term in extract_positioned_terms_for_page(words, 0):
        term_box = term.bbox.to_fractional()
        for row in rows:
            if int(row.id) in categories:
                continue
            box = _frac_box(row.bbox_json)
            if box is None:
                continue
            cx, cy = _center(box)
            if term_box[0] <= cx <= term_box[2] and term_box[1] <= cy <= term_box[3]:
                categories[int(row.id)] = term.term.category.value
    return categories


def build_master_perception(
    session: Session,
    master_id: int,
    *,
    page: int = 1,
    evidence_run_id: int | None = None,
) -> dict[str, Any] | None:
    drawing = session.get(Drawing, int(master_id))
    if drawing is None:
        return None

    warnings: list[str] = []
    rendition = (
        session.query(DrawingRendition)
        .filter(
            DrawingRendition.drawing_id == drawing.id,
            DrawingRendition.page_number == int(page),
        )
        .first()
    )
    width = float(rendition.width_px) if rendition is not None and rendition.width_px else 0.0
    height = float(rendition.height_px) if rendition is not None and rendition.height_px else 0.0
    if width <= 0 or height <= 0:
        width, height = 1000.0, 1000.0
        warnings.append(
            "Rendition pixel size is missing. Fractions are scaled onto a 1000×1000 canvas."
        )

    project = (
        session.query(Project).filter(Project.master_drawing_id == drawing.id).first()
    )
    image_url = (
        f"/api/projects/{project.id}/drawings/{drawing.id}/pages/{int(page)}/image"
        if project is not None
        else ""
    )
    if not image_url:
        warnings.append("This drawing is not a project's master, so no image URL was built.")

    text_rows = (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == drawing.id,
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id)
        .all()
    )
    categories = _classify_boxes(text_rows, width, height)
    ocr: list[dict[str, Any]] = []
    ocr_boxes: list[tuple[float, float, float, float]] = []
    for row in text_rows:
        box = _frac_box(row.bbox_json)
        if box is None:
            warnings.append(f"OCR text element {row.id} has no bounding box.")
            continue
        text = str(row.text or "")
        stations = extract_stations_from_text(text)
        station = stations[0] if stations else None
        item: dict[str, Any] = {
            "id": str(row.id),
            "text": text,
            "bbox": _px_box(box, width, height),
            "confidence": float(row.ocr_confidence or 0.0),
            "isStationLabel": station is not None,
            "source": str(row.source or ""),
        }
        category = categories.get(int(row.id))
        if category:
            item["category"] = category
        if station is not None:
            _stamp_station(item, station)
        ocr.append(item)
        ocr_boxes.append(box)

    for record in extract_station_control_points_from_elements(text_rows, max_plan_y=1.0):
        label_box = _frac_box(record.label_bbox_json)
        if label_box is None or not record.station:
            continue
        hit = False
        for item, box in zip(ocr, ocr_boxes):
            if _overlaps(box, label_box):
                _stamp_station(item, record.station)
                hit = True
        if hit:
            continue
        ocr.append(
            {
                "id": f"station-{record.station}",
                "text": record.station,
                "bbox": _px_box(label_box, width, height),
                "confidence": float(record.ocr_confidence or 0.0),
                "isStationLabel": True,
                "stationLabel": record.station,
                "parsedStation": _parsed_station(record.station),
                "source": "station_composition",
            }
        )
        ocr_boxes.append(label_box)
    warnings.append(
        "Station labels are composed from stored OCR with the indexer's joiner, across the whole page. The indexer itself only keeps stations above y=0.55."
    )

    survey_rows = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id == drawing.id, DrawingSurveyPoint.page == int(page))
        .order_by(DrawingSurveyPoint.id)
        .all()
    )
    control_points: list[dict[str, Any]] = []
    centers: list[tuple[float, float]] = []
    for row in survey_rows:
        box = _frac_box(row.label_bbox_json)
        if box is None:
            continue
        cx, cy = _center(box)
        centers.append((cx * width, cy * height))
        point: dict[str, Any] = {
            "id": str(row.id),
            "masterPt": _px_point(cx, cy, width, height),
            "origin": "manual" if str(row.source) == "manual" else "auto",
            "surveyNE": {"n": float(row.northing), "e": float(row.easting)},
        }
        if row.station:
            point["label"] = str(row.station)
        control_points.append(point)

    for row in survey_rows:
        if not row.station:
            continue
        sbox = _frac_box(row.label_bbox_json)
        if sbox is None:
            continue
        for item, box in zip(ocr, ocr_boxes):
            if _overlaps(box, sbox):
                _stamp_station(item, str(row.station))
        ocr.append(
            {
                "id": f"survey-station-{row.id}",
                "text": str(row.station),
                "bbox": _px_box(sbox, width, height),
                "confidence": float(row.ocr_confidence or 0.0),
                "isStationLabel": True,
                "stationLabel": str(row.station),
                "parsedStation": _parsed_station(str(row.station)),
                "source": "survey_point",
            }
        )
        ocr_boxes.append(sbox)

    symbols = (
        session.query(DrawingSymbol)
        .filter(DrawingSymbol.drawing_id == drawing.id, DrawingSymbol.page == int(page))
        .all()
    )
    ssmh: list[dict[str, Any]] = []
    for item, box in zip(ocr, ocr_boxes):
        if not _SSMH.search(str(item["text"])):
            continue
        cx, cy = _center(box)
        ssmh.append(
            {
                "id": f"ocr-{item['id']}",
                "label": str(item["text"]),
                "point": _px_point(cx, cy, width, height),
                "confidence": float(item["confidence"]),
                "source": "ocr_text",
            }
        )
    for row in symbols:
        label = str(row.symbol_class or "")
        if not _SSMH.search(label) and label.lower() not in {"ssmh", "manhole", "smh"}:
            continue
        box = _frac_box(row.bbox_json)
        if box is None:
            continue
        cx, cy = _center(box)
        ssmh.append(
            {
                "id": f"symbol-{row.id}",
                "label": label,
                "point": _px_point(cx, cy, width, height),
                "confidence": float(row.confidence or 0.0),
                "source": str(row.detector or row.symbol_class),
            }
        )
    for row in survey_rows:
        label = str(row.structure_label or "")
        if not _SSMH.search(label):
            continue
        box = _frac_box(row.label_bbox_json)
        if box is None:
            continue
        cx, cy = _center(box)
        ssmh.append(
            {
                "id": f"survey-{row.id}",
                "label": label,
                "point": _px_point(cx, cy, width, height),
                "surveyNE": {"n": float(row.northing), "e": float(row.easting)},
                "confidence": float(row.ocr_confidence or 0.0),
                "source": str(row.source or "survey"),
            }
        )

    stats = drawing.index_stats_json if isinstance(drawing.index_stats_json, dict) else {}
    graphs = stats.get("sheetEntityGraph") if isinstance(stats, dict) else None
    page_graph = graphs.get(str(int(page))) if isinstance(graphs, dict) else None
    stored_lines = load_page_lines(page_graph if isinstance(page_graph, dict) else None)
    pipes: list[dict[str, Any]] = []
    for index, line in enumerate(stored_lines):
        points = _line_points(line)
        if len(points) < 2:
            continue
        pipes.append(
            {
                "id": f"line-{index}",
                "polyline": [_px_point(x, y, width, height) for x, y in points],
                "source": "sheet_digitization",
                "confidence": float(line.get("confidence") or 0.0) if isinstance(line, dict) else 0.0,
            }
        )
    if not settings.sheet_digitization_enabled:
        warnings.append(
            "SHEET_DIGITIZATION_ENABLED=false — pipes are survey-chain approximations"
        )
    elif not pipes:
        warnings.append(
            "No sheet-digitized lines are stored for this page. Re-index with SHEET_DIGITIZATION_ENABLED=true."
        )

    landmarks = (
        session.query(DrawingLandmark)
        .filter(DrawingLandmark.drawing_id == drawing.id, DrawingLandmark.page == int(page))
        .all()
    )
    contours: list[dict[str, Any]] = []
    for row in landmarks:
        box = _frac_box(row.bbox_json)
        hu = row.hu_moments_json if isinstance(row.hu_moments_json, list) else []
        polygon = _region_polygon_from_box(box)
        contours.append(
            {
                "id": str(row.id),
                "points": [_px_point(x, y, width, height) for x, y in polygon],
                "huMoments": [float(v) for v in hu],
                "role": str(row.landmark_type or ""),
                "contourStored": False,
            }
        )
        if str(row.landmark_type) == "manhole" and box is not None:
            cx, cy = _center(box)
            ssmh.append(
                {
                    "id": f"landmark-{row.id}",
                    "label": "manhole",
                    "point": _px_point(cx, cy, width, height),
                    "confidence": float(row.ocr_confidence or 0.0),
                    "source": "landmark",
                }
            )
    warnings.append(
        "Landmark contours are not stored. Boxes and Hu moments are. The outline on the redraw is the stored bounding box."
    )
    warnings.append(
        "Canny edge maps are not computed or stored. Landmark extraction thresholds with Otsu and discards the image."
    )

    regions_out: list[dict[str, Any]] = []
    regions = (
        session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing.id, DrawingRegion.page == int(page))
        .all()
    )
    for row in regions:
        polygon = _region_polygon(row)
        tags = list(row.inspection_type_tags or []) + list(row.location_tags or [])
        regions_out.append(
            {
                "id": str(row.id),
                "name": str(row.label or ""),
                "polygon": [_px_point(x, y, width, height) for x, y in polygon],
                "status": "tagged" if tags else "untagged",
            }
        )

    overlay_query = session.query(DrawingOverlay).filter(
        DrawingOverlay.master_drawing_id == drawing.id
    )
    if evidence_run_id is not None:
        overlay_query = overlay_query.filter(
            DrawingOverlay.inspection_run_id == int(evidence_run_id)
        )
    overlays: list[dict[str, Any]] = []
    for row in overlay_query.all():
        geometry = row.geometry if isinstance(row.geometry, dict) else {}
        if int(geometry.get("page") or page) != int(page):
            continue
        meta = row.meta if isinstance(row.meta, dict) else {}
        source = str(meta.get("source") or "")
        for poly_index, poly in enumerate(_overlay_polylines(geometry)):
            overlays.append(
                {
                    "id": f"{row.id}-{poly_index}",
                    "regionId": str(row.region_id) if row.region_id is not None else None,
                    "polyline": [_px_point(x, y, width, height) for x, y in poly],
                    "evidenceRunId": str(row.inspection_run_id),
                    "source": source,
                }
            )
            if source in {"aux_survey_chain", "aux_survey_chain_projected", "survey_endpoints"}:
                pipes.append(
                    {
                        "id": f"overlay-{row.id}-{poly_index}",
                        "polyline": [_px_point(x, y, width, height) for x, y in poly],
                        "source": "survey_chain_fallback",
                        "confidence": None,
                    }
                )

    score = _collinearity(centers)
    count = len(control_points)
    if count < 3 or score >= _COLLINEAR:
        quality = "fail"
    elif score >= 0.75:
        quality = "warn"
    else:
        quality = "ok"
    if count < 3 or score >= _COLLINEAR:
        warnings.append(
            "Registration unreliable: control-point starvation"
            if count < 3
            else "Registration unreliable: control points are near-collinear"
        )

    transform: dict[str, float] | None = None
    run_key = ""
    if evidence_run_id is not None:
        run = session.get(InspectionRun, int(evidence_run_id))
        run_key = str(evidence_run_id)
        evidence = session.get(EvidenceRecord, run.evidence_id) if run and run.evidence_id else None
        meta = evidence.meta if evidence is not None and isinstance(evidence.meta, dict) else {}
        raw = meta.get("registration_transform")
        if isinstance(raw, dict):
            transform = {
                "scale": float(raw.get("scale_x") or raw.get("scale") or 0.0),
                "rotationDeg": float(raw.get("rotation_degrees") or raw.get("rotationDeg") or 0.0),
                "tx": float(raw.get("translate_x") or 0.0),
                "ty": float(raw.get("translate_y") or 0.0),
            }
        else:
            warnings.append(f"Evidence run {evidence_run_id} has no stored registration transform.")
        warnings.append("Per-point residuals and RMS are not persisted.")

    return {
        "master": {
            "id": str(drawing.id),
            "drawingNumber": str(drawing.name or ""),
            "page": int(page),
            "imageUrl": image_url,
            "widthPx": width,
            "heightPx": height,
            "projectId": project.id if project is not None else None,
        },
        "ocr": ocr,
        "ssmh": ssmh,
        "pipes": pipes,
        "edges": None,
        "contours": contours,
        "controlPoints": control_points,
        "registration": {
            "evidenceRunId": run_key,
            "transform": transform,
            "rmsResidualPx": None,
            "pointCount": count,
            "collinearityScore": score,
            "quality": quality,
        },
        "regions": regions_out,
        "overlays": overlays,
        "warnings": warnings,
    }


def _region_polygon_from_box(
    box: tuple[float, float, float, float] | None,
) -> list[tuple[float, float]]:
    if box is None:
        return []
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def list_master_drawings(session: Session, query: str | None = None) -> list[dict[str, Any]]:
    rows = (
        session.query(Drawing, Project)
        .join(Project, Project.master_drawing_id == Drawing.id)
        .order_by(Project.name, Drawing.name)
        .all()
    )
    needle = (query or "").strip().lower()
    found: list[dict[str, Any]] = []
    for drawing, project in rows:
        name = str(drawing.name or "")
        if needle and needle not in name.lower() and needle not in str(drawing.id):
            continue
        found.append(
            {
                "id": str(drawing.id),
                "drawingNumber": name,
                "projectId": project.id,
                "projectName": project.name,
            }
        )
    return found
