"""Structured failures for inspection placement (strict dev mode)."""

from __future__ import annotations

INSPECTION_NO_CANDIDATES = "INSPECTION_NO_CANDIDATES"
INSPECTION_NO_FUSED_WINNER = "INSPECTION_NO_FUSED_WINNER"
INSPECTION_NO_ANCHOR_BBOX = "INSPECTION_NO_ANCHOR_BBOX"
INSPECTION_NO_MASTER_SHEET_LINE = "INSPECTION_NO_MASTER_SHEET_LINE"
INSPECTION_NO_ANCHOR_INTERSECTING_LINE = "INSPECTION_NO_ANCHOR_INTERSECTING_LINE"
INSPECTION_INVALID_SCOPE = "INSPECTION_INVALID_SCOPE"
MASTER_SHEET_GRAPH_MISSING = "MASTER_SHEET_GRAPH_MISSING"
MASTER_SHEET_LINES_NOT_PLACABLE = "MASTER_SHEET_LINES_NOT_PLACABLE"


class InspectionPlacementError(Exception):
    """Placement could not complete without a fallback; run should fail visibly."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(self.format_message())

    def format_message(self) -> str:
        return f"[{self.code}] {self.message}"


def placement_strict_enabled() -> bool:
    from config import settings

    return bool(settings.inspection_placement_strict)


def inspection_placement_error_from_value_error(exc: ValueError) -> InspectionPlacementError:
    """Map ``[CODE] message`` ValueErrors from scope tracing to structured placement errors."""
    import re

    msg = str(exc)
    match = re.match(r"^\[([A-Z0-9_]+)\]\s*(.*)$", msg, flags=re.DOTALL)
    if match:
        return InspectionPlacementError(match.group(1), match.group(2).strip())
    return InspectionPlacementError(INSPECTION_NO_MASTER_SHEET_LINE, msg)
