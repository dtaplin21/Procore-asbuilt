"""Frontend-safe response schemas for inspection match status.

No confidence, score, or classification_confidence field is allowed here.
"""

from typing import Optional

from pydantic import BaseModel


class BboxResponse(BaseModel):
    x: float
    y: float
    width: float
    height: float


class InspectionMatchStatusResponse(BaseModel):
    inspection_id: str
    match_status: str  # matched | needs_review | no_match
    bbox: Optional[BboxResponse] = None
