from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from models.models import Drawing, DrawingAlignment, DrawingDiff
from models.schemas import (
    DrawingSummary,
    DrawingAlignmentResponse,
    DrawingDiffResponse,
    DrawingDiffRegion,
)
from services.file_storage import get_file_path
from services.storage import StorageService
from ai.pipelines.drawing_diff import run_drawing_diff

logger = logging.getLogger(__name__)

# Production validation thresholds
MIN_MATCHED_POINTS = 4
MIN_CONFIDENCE = 0.75
MAX_RESIDUAL_ERROR = 0.05
MIN_DET_FOR_INVERTIBLE = 1e-6
MAX_BOUNDS_SCALE = 10.0  # transformed unit square should stay within ~10x

try:
    import cv2  # type: ignore
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _CV2_AVAILABLE = False

try:
    import fitz  # type: ignore  # pymupdf
    _FITZ_AVAILABLE = True
except ImportError:
    fitz = None  # type: ignore[assignment]
    _FITZ_AVAILABLE = False


class DrawingComparisonService:
    def __init__(self, db):
        self.db = db
        self.storage = StorageService(db)

    def _serialize_drawing(self, drawing: Drawing) -> DrawingSummary:
        return DrawingSummary(
            id=cast(int, drawing.id),
            project_id=cast(int, drawing.project_id),
            source=getattr(drawing, "source", None),
            name=cast(str, drawing.name),
            file_url=getattr(drawing, "file_url", None),
            content_type=getattr(drawing, "content_type", None),
            page_count=getattr(drawing, "page_count", None),
        )

    def _serialize_alignment(self, alignment: DrawingAlignment) -> DrawingAlignmentResponse:
        project_id = None
        if alignment.master_drawing is not None:
            project_id = cast(int, alignment.master_drawing.project_id)
        return DrawingAlignmentResponse(
            id=cast(int, alignment.id),
            project_id=project_id,
            master_drawing_id=cast(int, alignment.master_drawing_id),
            sub_drawing_id=cast(int, alignment.sub_drawing_id),
            transform_matrix=getattr(alignment, "transform_matrix", None) or getattr(alignment, "transform", None),
            alignment_status=getattr(alignment, "alignment_status", None) or getattr(alignment, "status", None),
            created_at=alignment.created_at.isoformat() if getattr(alignment, "created_at", None) else None,
        )

    def _serialize_diff(self, diff: DrawingDiff) -> DrawingDiffResponse:
        raw_regions = getattr(diff, "diff_regions", None) or []

        diff_regions = [
            DrawingDiffRegion(
                page=region.get("page"),
                bbox=region.get("bbox"),
                change_type=region.get("change_type") or region.get("type"),
                note=region.get("note") or region.get("label"),
            )
            for region in raw_regions
        ]

        return DrawingDiffResponse(
            id=cast(int, diff.id),
            alignment_id=cast(int, diff.alignment_id),
            summary=getattr(diff, "summary", None),
            status=getattr(diff, "severity", None),
            diff_regions=diff_regions,
            created_at=diff.created_at.isoformat() if getattr(diff, "created_at", None) else None,
        )

    def _validate_project_drawings(
        self, project_id: int, master_drawing_id: int, sub_drawing_id: int
    ) -> tuple[Drawing, Drawing]:
        master_drawing = self.storage.get_drawing(project_id, master_drawing_id)
        sub_drawing = self.storage.get_drawing(project_id, sub_drawing_id)

        if not master_drawing:
            raise ValueError(f"Master drawing {master_drawing_id} not found")

        if not sub_drawing:
            raise ValueError(f"Sub drawing {sub_drawing_id} not found")

        if cast(int, master_drawing.project_id) != project_id:
            raise ValueError(
                f"Master drawing {master_drawing_id} does not belong to project {project_id}"
            )

        if cast(int, sub_drawing.project_id) != project_id:
            raise ValueError(
                f"Sub drawing {sub_drawing_id} does not belong to project {project_id}"
            )

        if cast(int, master_drawing.id) == cast(int, sub_drawing.id):
            raise ValueError("Master drawing and sub drawing must be different")

        return master_drawing, sub_drawing

    def build_fallback_identity_transform(self, page: int = 1) -> Dict[str, Any]:
        """
        Fallback only when: master==sub duplicate, user chooses manual identity,
        or no geometric processing is possible. Not the default production path.
        """
        return {
            "type": "identity",
            "matrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "confidence": 0.0,
            "residual_error": None,
            "page": page,
        }

    def render_drawing_page(self, drawing: Drawing, page: int = 1) -> Optional[Any]:
        """
        Render a drawing page to a grayscale numpy image.
        Supports PDF (via pymupdf) and raster images (PNG, JPEG via OpenCV).
        Returns (H, W) uint8 array or None if render fails.
        """
        if not _CV2_AVAILABLE or cv2 is None or np is None:
            return None

        storage_key = getattr(drawing, "storage_key", None)
        if not storage_key:
            return None

        try:
            path = get_file_path(storage_key)
        except Exception:
            return None

        if not path.exists():
            return None

        suffix = path.suffix.lower()
        content_type = getattr(drawing, "content_type", "") or ""

        if suffix == ".pdf" or "pdf" in content_type:
            if _FITZ_AVAILABLE and fitz is not None:
                try:
                    doc = fitz.open(str(path))
                    if page < 1 or page > len(doc):
                        page = 1
                    pix = doc.load_page(page - 1).get_pixmap(dpi=150, alpha=False)
                    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width, pix.n
                    )
                    doc.close()
                    if img.ndim == 3 and pix.n == 3:
                        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    elif img.ndim == 3 and pix.n == 1:
                        img = img.squeeze(-1)
                    return img
                except Exception as e:
                    logger.warning("PDF render failed: %s", e)
                    return None
            return None

        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        return img if img is not None else None

    def extract_features(self, image: Any) -> Dict[str, Any]:
        """
        Extract keypoints and descriptors from a grayscale image (numpy array).
        Returns dict with keypoints, descriptors, shape, num_features.
        """
        if not _CV2_AVAILABLE or cv2 is None or np is None:
            return {}

        if image is None or not hasattr(image, "shape"):
            return {}

        assert cv2 is not None and np is not None
        detector = cv2.ORB_create(nfeatures=2000)
        kpts, descs = detector.detectAndCompute(image, None)
        if descs is None:
            descs = np.array([])
        return {
            "keypoints": kpts,
            "descriptors": descs,
            "shape": list(image.shape),
            "num_features": len(kpts),
        }

    def extract_alignment_features(self, master_path: str, sub_path: str) -> Dict[str, Any]:
        """
        Extract keypoints and descriptors from master and sub images.
        Returns {"master": {...}, "sub": {...}} with keys, descriptors, shape per image.
        """
        if not _CV2_AVAILABLE or cv2 is None or np is None:
            logger.warning("OpenCV not available; returning empty features")
            return {"master": {}, "sub": {}}

        def _extract(path: str) -> Dict[str, Any]:
            assert cv2 is not None and np is not None
            p = Path(path)
            if not p.exists():
                return {}
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is None:
                return {}
            detector = cv2.ORB_create(nfeatures=2000)
            kpts, descs = detector.detectAndCompute(img, None)
            if descs is None:
                descs = np.array([])
            return {
                "keypoints": kpts,
                "descriptors": descs,
                "shape": list(img.shape),
                "num_features": len(kpts),
            }

        return {
            "master": _extract(master_path),
            "sub": _extract(sub_path),
        }

    def match_alignment_features(
        self, master_features: Dict[str, Any], sub_features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Match descriptors between master and sub. Returns source_points, target_points
        (normalized 0-1), and raw matches for RANSAC.
        """
        if not _CV2_AVAILABLE or cv2 is None:
            return {"source_points": [], "target_points": [], "matches": []}

        m_desc = master_features.get("descriptors")
        s_desc = sub_features.get("descriptors")
        m_kpts = master_features.get("keypoints", [])
        s_kpts = sub_features.get("keypoints", [])

        if m_desc is None or s_desc is None or len(m_desc) < 4 or len(s_desc) < 4:
            return {"source_points": [], "target_points": [], "matches": []}

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        raw_matches = matcher.knnMatch(m_desc, s_desc, k=2)

        good = []
        for pair in raw_matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < 0.75 * n.distance:
                    good.append(m)

        if len(good) < 4:
            return {"source_points": [], "target_points": [], "matches": []}

        source_pts = []
        target_pts = []
        for m in good:
            pt_m = m_kpts[m.queryIdx].pt
            pt_s = s_kpts[m.trainIdx].pt
            source_pts.append({"x": float(pt_m[0]), "y": float(pt_m[1])})
            target_pts.append({"x": float(pt_s[0]), "y": float(pt_s[1])})

        return {
            "source_points": source_pts,
            "target_points": target_pts,
            "matches": good,
        }

    def estimate_transform(self, matches: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate homography from matched points. Uses RANSAC.
        Returns production transform: type, matrix [h11..h33], confidence, page.
        Homography handles perspective, skew, and scanning distortions.
        """
        if not _CV2_AVAILABLE or cv2 is None or np is None:
            return self.build_fallback_identity_transform()

        src = matches.get("source_points", [])
        tgt = matches.get("target_points", [])

        if len(src) < 4 or len(tgt) < 4:
            return self.build_fallback_identity_transform()

        src_arr = np.array([[p["x"], p["y"]] for p in src], dtype=np.float32)
        tgt_arr = np.array([[p["x"], p["y"]] for p in tgt], dtype=np.float32)

        H, mask = cv2.findHomography(tgt_arr, src_arr, cv2.RANSAC, 5.0)

        if H is None:
            return self.build_fallback_identity_transform()

        matrix = H.flatten().tolist()
        inliers = int(mask.sum()) if mask is not None else 0
        total = len(src)
        confidence = float(inliers / total) if total else 0.0

        return {
            "type": "homography",
            "matrix": matrix,
            "confidence": confidence,
            "source_points": src,
            "target_points": tgt,
            "page": 1,
        }

    def validate_transform(
        self,
        transform: Dict[str, Any],
        expected_page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate transform for production: enough points, confidence, residual,
        invertibility, plausible bounds. Raises ValueError if validation fails.
        Returns enriched transform with residual_error.
        """
        if not transform:
            raise ValueError("Missing transform")

        matrix = transform.get("matrix")
        if not matrix or len(matrix) != 9:
            raise ValueError("Missing or invalid transform matrix (expected 9 elements)")

        src = transform.get("source_points", [])
        tgt = transform.get("target_points", [])

        if len(src) < MIN_MATCHED_POINTS or len(tgt) < MIN_MATCHED_POINTS:
            raise ValueError(
                f"Insufficient matched points (need at least {MIN_MATCHED_POINTS}, "
                f"got {len(src)}/{len(tgt)})"
            )

        confidence = transform.get("confidence", 0.0)
        if confidence < MIN_CONFIDENCE:
            raise ValueError(
                f"Alignment confidence {confidence:.2f} below threshold {MIN_CONFIDENCE}"
            )

        if expected_page is not None:
            page = transform.get("page")
            if page is not None and page != expected_page:
                raise ValueError(f"Page mismatch: expected {expected_page}, got {page}")

        if not _CV2_AVAILABLE or np is None:
            return {**transform, "residual_error": None}

        assert np is not None
        H = np.array(matrix, dtype=np.float32).reshape(3, 3)

        det = float(np.linalg.det(H))
        if abs(det) < MIN_DET_FOR_INVERTIBLE:
            raise ValueError(f"Transform not invertible (det={det:.2e})")

        src_arr = np.array([[p["x"], p["y"]] for p in src], dtype=np.float32)
        tgt_arr = np.array([[p["x"], p["y"]] for p in tgt], dtype=np.float32)
        tgt_h = np.column_stack([tgt_arr, np.ones(len(tgt_arr))])

        projected = (H @ tgt_h.T).T
        projected = projected[:, :2] / projected[:, 2:3]
        diff = src_arr - projected
        residual_error = float(np.sqrt((diff ** 2).sum(axis=1).mean()))

        if residual_error > MAX_RESIDUAL_ERROR:
            raise ValueError(
                f"Residual error {residual_error:.4f} exceeds threshold {MAX_RESIDUAL_ERROR}"
            )

        unit_corners = np.array(
            [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float32
        )
        transformed = (H @ unit_corners.T).T
        transformed = transformed[:, :2] / transformed[:, 2:3]
        extent = np.ptp(transformed, axis=0)
        max_extent = float(np.max(extent))
        if max_extent > MAX_BOUNDS_SCALE:
            raise ValueError(
                f"Transformed bounds implausible (extent {max_extent:.2f} > {MAX_BOUNDS_SCALE})"
            )

        return {
            **transform,
            "residual_error": residual_error,
        }

    def compare(
        self,
        project_id: int,
        master_drawing_id: int,
        sub_drawing_id: int,
        *,
        force_recompute: bool = False,
    ) -> Dict[str, Any]:
        """
        Main orchestration: validate, load/create alignment, reuse or compute transform,
        run diff pipeline, return serialized workspace.
        """
        master_drawing, sub_drawing = self._validate_project_drawings(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
        )

        alignment = self.storage.get_alignment_by_drawing_pair(
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
        )

        if not alignment:
            has_files = bool(
                getattr(master_drawing, "storage_key", None)
                and getattr(sub_drawing, "storage_key", None)
            )
            method = "feature_match" if has_files else "manual"
            alignment = self.storage.create_drawing_alignment(
                master_drawing_id=master_drawing_id,
                sub_drawing_id=sub_drawing_id,
                method=method,
                region_id=None,
            )

        if force_recompute:
            transform = None
        else:
            existing = self.storage.get_reusable_alignment(
                master_drawing_id=master_drawing_id,
                sub_drawing_id=sub_drawing_id,
            )
            if existing and getattr(existing, "transform", None):
                transform = existing.transform
            else:
                transform = None

        if transform is None:
            run_alignment_lifecycle(self.db, alignment, master_drawing, sub_drawing)
            self.storage.db.refresh(alignment)

        diffs = self.storage.list_drawing_diffs_by_alignment(cast(int, alignment.id))

        if force_recompute or not diffs:
            new_diffs = run_drawing_diff(self.db, alignment=alignment)
            if new_diffs:
                diffs = new_diffs
            else:
                diffs = self.storage.list_drawing_diffs_by_alignment(
                    cast(int, alignment.id)
                )

        return {
            "master_drawing": self._serialize_drawing(master_drawing),
            "sub_drawing": self._serialize_drawing(sub_drawing),
            "alignment": self._serialize_alignment(alignment),
            "diffs": [self._serialize_diff(diff) for diff in diffs],
        }

    def compute_alignment_transform(
        self,
        master_drawing: Drawing,
        sub_drawing: Drawing,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        Production alignment flow: render page images -> extract features ->
        match descriptors -> estimate homography -> validate.
        Returns transform dict suitable for drawing_alignments.transform.
        """
        master_image = self.render_drawing_page(master_drawing, page)
        sub_image = self.render_drawing_page(sub_drawing, page)

        if master_image is None or sub_image is None:
            logger.warning("Failed to render drawing pages; using fallback identity")
            return self.build_fallback_identity_transform(page)

        master_features = self.extract_features(master_image)
        sub_features = self.extract_features(sub_image)

        if master_features.get("num_features", 0) < 4 or sub_features.get("num_features", 0) < 4:
            logger.warning("Insufficient features; using fallback identity")
            return self.build_fallback_identity_transform(page)

        matches = self.match_alignment_features(master_features, sub_features)
        if not matches.get("source_points") or len(matches["source_points"]) < 4:
            logger.warning("Insufficient matches; using fallback identity")
            return self.build_fallback_identity_transform(page)

        transform = self.estimate_transform(matches)
        transform["page"] = page
        try:
            validated = self.validate_transform(transform, expected_page=page)
        except ValueError as e:
            logger.warning("Transform validation failed: %s; using fallback identity", e)
            return self.build_fallback_identity_transform(page)
        return _to_production_transform(validated)


def _to_production_transform(transform: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return canonical production homography shape:
    type, matrix [h11..h33], confidence, residual_error, page.
    """
    return {
        "type": transform.get("type", "homography"),
        "matrix": transform.get("matrix", [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]),
        "confidence": transform.get("confidence"),
        "residual_error": transform.get("residual_error"),
        "page": transform.get("page", 1),
    }


def _serialize_drawing(drawing: Drawing) -> Dict[str, Any]:
    return {
        "id": drawing.id,
        "project_id": drawing.project_id,
        "source": drawing.source,
        "name": drawing.name,
        "file_url": getattr(drawing, "file_url", None),
        "content_type": getattr(drawing, "content_type", None),
        "page_count": getattr(drawing, "page_count", None),
    }


def _validate_project_drawings(
    storage: StorageService,
    *,
    project_id: int,
    master_drawing_id: int,
    sub_drawing_id: int,
) -> tuple[Drawing, Drawing]:
    master = storage.get_drawing(project_id=project_id, drawing_id=master_drawing_id)
    if master is None:
        raise ValueError("Master drawing not found for project")

    sub = storage.get_drawing(project_id=project_id, drawing_id=sub_drawing_id)
    if sub is None:
        raise ValueError("Sub drawing not found for project")

    if cast(int, master.project_id) != project_id or cast(int, sub.project_id) != project_id:
        raise ValueError("Drawings do not belong to the requested project")

    if cast(int, master.id) == cast(int, sub.id):
        raise ValueError("Master drawing and sub drawing must be different")

    return master, sub


def run_alignment_lifecycle(
    db: Session,
    alignment: DrawingAlignment,
    master_drawing: Drawing,
    sub_drawing: Drawing,
    *,
    page: int = 1,
) -> None:
    """
    Run alignment pipeline with proper lifecycle: processing -> complete/failed.
    Updates alignment status via storage.update_alignment_status.
    """
    storage = StorageService(db)
    svc = DrawingComparisonService(db)
    alignment_id = cast(int, alignment.id)

    storage.update_alignment_status(alignment_id, "processing")
    try:
        transform = svc.compute_alignment_transform(master_drawing, sub_drawing, page=page)
        storage.update_alignment_status(alignment_id, "complete", transform=transform)
    except Exception as e:
        storage.update_alignment_status(
            alignment_id, "failed", error_message=str(e)
        )
        raise


def compare_sub_drawing_to_master(
    db: Session,
    *,
    project_id: int,
    master_drawing_id: int,
    sub_drawing_id: int,
    force_recompute: bool = False,
) -> Dict[str, Any]:
    """
    Compare sub drawing to master. Validates, loads/creates alignment,
    reuses or computes transform, persists, runs diff pipeline.
    """
    svc = DrawingComparisonService(db)
    return svc.compare(
        project_id=project_id,
        master_drawing_id=master_drawing_id,
        sub_drawing_id=sub_drawing_id,
        force_recompute=force_recompute,
    )
