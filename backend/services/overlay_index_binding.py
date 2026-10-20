"""Bind an inspection overlay to the master index it was placed against.

A later re-index must not keep drawing geometry that was computed from the
previous sheet graph. Overlays store ``built_from_indexed_at``. Rows written
before that stamp are current only when they were saved at or after
``drawings.indexed_at``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.drawing_overlay import DrawingOverlay
from models.schemas import DrawingOverlayResponse

BUILT_FROM_INDEXED_AT_KEY = "built_from_indexed_at"
INDEX_STALE_KEY = "index_stale"

_STALE_GEOMETRY: dict[str, Any] = {"page": 1, "type": "none"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # Timestamp columns are stored without a zone and reload as local wall time.
        return value.astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def index_revision_stamp(value: datetime | None) -> str | None:
    """Stable UTC timestamp string for comparing index revisions."""
    normalized = _as_utc(value)
    if normalized is None:
        return None
    return normalized.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def with_index_stamp(meta: dict[str, Any] | None, indexed_at: datetime | None) -> dict[str, Any]:
    stamped = dict(meta or {})
    stamped.pop(INDEX_STALE_KEY, None)
    stamp = index_revision_stamp(indexed_at)
    if stamp is None:
        stamped.pop(BUILT_FROM_INDEXED_AT_KEY, None)
    else:
        stamped[BUILT_FROM_INDEXED_AT_KEY] = stamp
    return stamped


def overlay_matches_current_index(
    meta: Any,
    *,
    indexed_at: datetime | None,
    overlay_created_at: datetime | None,
) -> bool:
    """True when this overlay was produced from the drawing's current index."""
    current = index_revision_stamp(indexed_at)
    if current is None:
        return True
    if isinstance(meta, dict):
        stamped = meta.get(BUILT_FROM_INDEXED_AT_KEY)
        if isinstance(stamped, str) and stamped:
            return stamped == current
    created = _as_utc(overlay_created_at)
    indexed = _as_utc(indexed_at)
    if created is None or indexed is None:
        return False
    return created >= indexed


def overlay_response_for_index(
    overlay: DrawingOverlay,
    indexed_at: datetime | None,
) -> DrawingOverlayResponse:
    """Drop placement geometry when the overlay belongs to an older index."""
    response = DrawingOverlayResponse.model_validate(overlay)
    if overlay_matches_current_index(
        overlay.meta,
        indexed_at=indexed_at,
        overlay_created_at=overlay.created_at,
    ):
        return response
    meta = dict(response.meta or {})
    meta[INDEX_STALE_KEY] = True
    return response.model_copy(update={"geometry": dict(_STALE_GEOMETRY), "meta": meta})
