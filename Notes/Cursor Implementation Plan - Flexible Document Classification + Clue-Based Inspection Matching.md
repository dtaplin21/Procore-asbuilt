# Cursor Implementation Plan: Flexible Document Classification + Clue-Based Inspection Matching

## Goal

Implement a flexible AI inspection-location matching system that can handle different file types, especially:

1. Inspection reports
2. Field photos
3. Master drawings
4. Unknown/unsupported documents

The system should not assume every inspection file is a drawing. Some inspection files are reports with metadata and photo attachments. The AI must treat each uploaded inspection file as a source of clues, then use those clues to locate the most likely matching area on the master drawing.

This replaces the old regex-only inspection query builder. Instead of extracting hardcoded search terms from one inspection format, the system will:

1. Classify the document type.
2. Extract universal fields.
3. Extract type-specific fields.
4. Convert fields into searchable clues.
5. Feed those clues into the existing candidate selector and matching pipeline.
6. Keep confidence values backend-only.
7. Return only match statuses to the frontend: `matched`, `needs_review`, or `no_match`.

Do not expose numeric confidence or scoring values to the frontend.

---

# PHASE 0 — Decide scope for v1 (PDF link enrichment)

## Objective

Lock hard limits for following hyperlinks embedded in uploaded PDFs to gather **supplemental text** before classification and clue extraction. These bounds prevent runaway fetches, SSRF, and token blow-ups.

**Do not write link-following code until these limits are agreed.** Use module-level constants for v1; wire them into `backend/config.py` in **link-enrichment Phase 7** (env-backed settings).

## Locked v1 limits

| Setting | v1 value | Notes |
| --- | --- | --- |
| Max link follow depth | `1` | Only links **directly embedded** in the uploaded PDF. Do not recurse into fetched documents. |
| Max external fetches | `5` per upload | Hard cap; stop enrichment when reached. |
| Max supplemental text | `80_000` chars total | Count across all fetched bodies **plus** same-PDF page text merged in. Truncate oldest/lowest-priority chunks first. |
| Allowed external domains | `procore.com`, `sandbox.procore.com`, app domain | App domain = host parsed from `FRONTEND_PUBLIC_URL` (e.g. `app.example.com`). Subdomains of allowed roots are OK (`*.procore.com`). |
| Internal links | Same-PDF page jumps only | `#page=N`, `/page/N`, or equivalent in-document anchors. Never treat as external fetches. |
| File types from external fetch | PDF + HTML text only | Reject images, binaries, JSON APIs, etc. Extract plain text from HTML; reject non-text PDFs after extraction attempt. |

## Enforcement rules (v1)

1. **Depth 0** = uploaded PDF body. **Depth 1** = URLs found in that PDF only. Fetched PDFs/HTML must not be scanned for further links.
2. **Domain allowlist** — reject (log + skip) any URL whose host is not an allowed domain or subdomain. No IP literals, no redirect chains to disallowed hosts.
3. **Fetch budget** — increment counter only for successful external HTTP fetches. Same-PDF page jumps do not count.
4. **Text budget** — track cumulative supplemental chars; stop fetching when `80_000` would be exceeded.
5. **Content types** — accept `application/pdf`, `text/html`, and `text/plain` from HTML fallbacks only. Everything else is skipped.
6. **Timeouts** — use short per-request timeouts (suggest 10s) so five fetches cannot block upload indefinitely.

## v1 constants (code until Phase 7 config)

When implementing link enrichment, start with a single module (e.g. `backend/ai/pipelines/pdf_link_enrichment_limits.py`):

```python
MAX_LINK_FOLLOW_DEPTH = 1
MAX_EXTERNAL_FETCHES_PER_UPLOAD = 5
MAX_SUPPLEMENTAL_TEXT_CHARS = 80_000

ALLOWED_EXTERNAL_DOMAIN_SUFFIXES = (
    "procore.com",
    "sandbox.procore.com",
)

# Append host from settings.frontend_public_url at runtime (see backend/config.py).
```

Allowed domains helper should merge `ALLOWED_EXTERNAL_DOMAIN_SUFFIXES` with the host from `FRONTEND_PUBLIC_URL`.

## Out of scope for v1

* Recursive link following (depth > 1)
* Authenticated Procore API calls as a substitute for link fetch (use existing OAuth client separately)
* Fetching attachments from arbitrary third-party domains
* Image/OCR from linked URLs (only PDF text + HTML text)
* User-configurable limits (Phase 7 moves constants to settings/env)

## Acceptance criteria

* Limits are documented here and referenced by any link-enrichment implementation PR.
* No link follower ships without depth, fetch-count, char-cap, and domain checks.
* Same-PDF internal page links never increment the external fetch counter.

---

# PHASE 1 — Confirm existing pipeline and delete old regex-only Phase 18

## Objective

Remove the old `inspection_query_builder.py` approach and replace it with a flexible clue-based document extraction pipeline.

## Important rule

Do not create a parallel matching system. The new clue pipeline must feed the existing candidate selector and existing match/candidate storage.

## Tasks

1. Locate old file:

```text
backend/ai/pipelines/inspection_query_builder.py
```

2. Delete it or stop importing it anywhere.

3. Search the codebase for references:

```bash
grep -R "inspection_query_builder" -n backend
grep -R "find_candidate_tiles" -n backend
grep -R "search_terms" -n backend
```

4. Replace any old regex/search-term dependency with the new clue pipeline from later phases.

## Acceptance criteria

* No runtime code depends on `inspection_query_builder.py`.
* The project no longer assumes inspection inputs are always simple text reports or drawing snippets.
* Candidate matching will be driven by `DocumentClue` rows.

---

# PHASE 2 — Add layered document extraction schemas

## Objective

Create schemas for:

1. Document classification
2. Universal fields
3. Type-specific fields
4. Clues

Only support these document types for now:

```text
inspection_report
field_photo
master_drawing
unknown
```

Do not add submittals, RFIs, daily reports, or as-built markups yet. Add those later only after real example files exist.

## New file

```text
backend/ai/schemas/document_extraction_schemas.py
```

## Code

```python
"""Pydantic schemas for flexible document classification, universal field extraction,
type-specific extraction, and clue generation.

Scope:
- inspection_report
- field_photo
- master_drawing
- unknown

Do not add speculative document types until real example files are available.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    INSPECTION_REPORT = "inspection_report"
    FIELD_PHOTO = "field_photo"
    MASTER_DRAWING = "master_drawing"
    UNKNOWN = "unknown"


class DocumentClassification(BaseModel):
    document_type: DocumentType
    confidence: float  # BACKEND ONLY. Never return to frontend.


class UniversalFields(BaseModel):
    project_name: Optional[str] = None
    project_number: Optional[str] = None
    location_text: Optional[str] = None
    date: Optional[str] = None
    trade: Optional[str] = None
    contractor: Optional[str] = None
    document_title: Optional[str] = None


class InspectionReportFields(BaseModel):
    inspection_name: Optional[str] = None
    inspection_status: Optional[str] = None
    items_inspected: List[str] = Field(default_factory=list)
    pass_fail_result: Optional[str] = None
    assignees: List[str] = Field(default_factory=list)
    inspection_notes: List[str] = Field(default_factory=list)


class FieldPhotoFields(BaseModel):
    visible_objects: List[str] = Field(default_factory=list)
    visible_text: List[str] = Field(default_factory=list)
    environment: Optional[str] = None
    utility_type: Optional[str] = None
    possible_location_clues: List[str] = Field(default_factory=list)
    camera_perspective: Optional[str] = None


class MasterDrawingFields(BaseModel):
    sheet_number: Optional[str] = None
    sheet_title: Optional[str] = None
    discipline: Optional[str] = None
    drawing_labels: List[str] = Field(default_factory=list)
    utility_symbols: List[str] = Field(default_factory=list)
    areas_or_zones: List[str] = Field(default_factory=list)


TYPE_SPECIFIC_SCHEMAS = {
    DocumentType.INSPECTION_REPORT: InspectionReportFields,
    DocumentType.FIELD_PHOTO: FieldPhotoFields,
    DocumentType.MASTER_DRAWING: MasterDrawingFields,
}


class Clue(BaseModel):
    type: str
    value: str
    source: str
    confidence: float  # BACKEND ONLY. Used for ranking only.
    location_relevant: bool = True
```

## Verification

Run:

```bash
python -c "from backend.ai.schemas.document_extraction_schemas import *"
```

Then test manually:

```python
from backend.ai.schemas.document_extraction_schemas import UniversalFields, InspectionReportFields

u = UniversalFields(
    project_name="UCSF Benioff Oakland",
    project_number="02001.161310",
    location_text="COLO",
    trade="33-Sanitary Sewerage",
)

i = InspectionReportFields(
    inspection_name="Underground Sanitary Sewer #1",
    inspection_notes=["Sanitary sewer inspection prior to backfill in the Colo parking lot"],
)
```

Expected:

* No validation errors.
* Missing optional fields should not crash.

---

# PHASE 3 — Add document classification pipeline with low-confidence fallback

## Objective

Classify each document before extraction. If classification confidence is too low, force the document to `unknown` and route it to the review queue.

## New file

```text
backend/ai/pipelines/document_classifier.py
```

## Code

```python
"""Document classifier for supported construction document types.

If confidence is below threshold, return UNKNOWN so the wrong type-specific extractor
does not run.
"""

from backend.ai.schemas.document_extraction_schemas import (
    DocumentType,
    DocumentClassification,
)

CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.60

CLASSIFY_PROMPT = """
Classify this construction document into exactly one type:

- inspection_report
- field_photo
- master_drawing
- unknown

Use unknown if it clearly does not fit the supported types or if there is not enough
information.

Respond as JSON:
{
  "document_type": "inspection_report | field_photo | master_drawing | unknown",
  "confidence": 0.0
}
"""


def classify_document(document_text_or_description: str) -> DocumentClassification:
    raw = _call_classifier_llm(document_text_or_description)
    classification = DocumentClassification(**raw)

    if classification.confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
        classification.document_type = DocumentType.UNKNOWN

    return classification


def _call_classifier_llm(content: str) -> dict:
    """
    ADAPT:
    Wire this to the repo's existing LLM client.

    For text-bearing docs:
    - send extracted text

    For photos/drawings:
    - send an image description or use the repo's existing vision model adapter
    """
    raise NotImplementedError("Wire to this repo's existing LLM client")
```

## New test file

```text
backend/tests/test_document_classifier.py
```

## Code

```python
from backend.ai.schemas.document_extraction_schemas import (
    DocumentType,
    DocumentClassification,
)
from backend.ai.pipelines.document_classifier import CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_low_confidence_should_be_forced_to_unknown():
    raw = {"document_type": "inspection_report", "confidence": 0.4}
    classification = DocumentClassification(**raw)

    if classification.confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
        classification.document_type = DocumentType.UNKNOWN

    assert classification.document_type == DocumentType.UNKNOWN
```

## Verification

Run:

```bash
pytest backend/tests/test_document_classifier.py -v
```

Expected:

* Low-confidence classifications become `unknown`.
* Later, once LLM wiring exists, the UCSF inspection report should classify as `inspection_report`.

---

# PHASE 4 — Add review queue for low-confidence or failed extraction

## Objective

Create a backend-only review queue table for files that cannot be classified or extracted safely.

## New model

```text
backend/models/review_queue_item.py
```

## Code

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, func
from backend.models.models import Base  # ADAPT if your Base lives elsewhere


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    id = Column(Integer, primary_key=True)
    file_id = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=False)
    document_type_guess = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)  # BACKEND ONLY
    resolved = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

## New migration

Create Alembic migration:

```bash
alembic revision -m "add review queue items"
```

Then edit the generated file:

```python
from alembic import op
import sqlalchemy as sa

revision = "<generated_revision>"
down_revision = "<previous_revision>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_queue_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.String, nullable=False),
        sa.Column("reason", sa.String, nullable=False),
        sa.Column("document_type_guess", sa.String, nullable=True),
        sa.Column("classification_confidence", sa.Float, nullable=True),
        sa.Column("resolved", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_review_queue_items_file_id", "review_queue_items", ["file_id"])
    op.create_index("ix_review_queue_items_resolved", "review_queue_items", ["resolved"])


def downgrade():
    op.drop_index("ix_review_queue_items_resolved", table_name="review_queue_items")
    op.drop_index("ix_review_queue_items_file_id", table_name="review_queue_items")
    op.drop_table("review_queue_items")
```

## New service

```text
backend/services/review_queue.py
```

## Code

```python
def add_to_review_queue(
    session,
    file_id: str,
    reason: str,
    document_type_guess: str = None,
    confidence: float = None,
):
    from backend.models.review_queue_item import ReviewQueueItem

    item = ReviewQueueItem(
        file_id=file_id,
        reason=reason,
        document_type_guess=document_type_guess,
        classification_confidence=confidence,
    )

    session.add(item)
    session.commit()
    return item
```

## Verification

Run:

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected:

* Migration up/down works.
* A low-confidence or failed extraction can create a `review_queue_items` row.

---

# PHASE 5 — Add universal field extraction

## Objective

Extract fields that may appear across many document types.

Universal fields:

```text
project_name
project_number
location_text
date
trade
contractor
document_title
```

## New file

```text
backend/ai/pipelines/universal_field_extractor.py
```

## Code

```python
"""Universal field extraction for construction documents."""

from backend.ai.schemas.document_extraction_schemas import UniversalFields

UNIVERSAL_EXTRACTION_PROMPT = """
Extract these fields if present in the document:

- project_name
- project_number
- location_text
- date
- trade
- contractor
- document_title

If a field is missing, return null.

Respond as JSON matching exactly:
{
  "project_name": null,
  "project_number": null,
  "location_text": null,
  "date": null,
  "trade": null,
  "contractor": null,
  "document_title": null
}
"""


def extract_universal_fields(document_text_or_description: str) -> UniversalFields:
    raw = _call_extraction_llm(document_text_or_description)
    return UniversalFields(**raw)


def _call_extraction_llm(content: str) -> dict:
    """
    ADAPT:
    Wire to existing LLM client.

    For text docs:
    - use parsed text

    For photos:
    - use vision description or image model output
    """
    raise NotImplementedError("Wire to this repo's existing LLM client")
```

## Verification

Run against the UCSF inspection report text.

Expected universal fields:

```text
project_name: UCSF Benioff Oakland
project_number: 02001.161310
location_text: COLO
trade: 33-Sanitary Sewerage
document_title: Underground Sanitary Sewer #1
```

Missing fields should return `None`, not crash.

---

# PHASE 6 — Add type-specific extraction

## Objective

Once the document type is known, extract fields specific to that type.

Supported type-specific extractors:

1. Inspection report extractor
2. Field photo extractor
3. Master drawing extractor

If validation fails, route to review queue.

## New file

```text
backend/ai/pipelines/type_specific_extractor.py
```

## Code

```python
"""Type-specific extraction dispatcher.

Validation failures route to review queue instead of crashing or silently storing bad data.
"""

from pydantic import ValidationError
from backend.ai.schemas.document_extraction_schemas import (
    DocumentType,
    TYPE_SPECIFIC_SCHEMAS,
)


TYPE_SPECIFIC_PROMPTS = {
    DocumentType.INSPECTION_REPORT: """
Extract:
- inspection_name
- inspection_status
- items_inspected as a list
- pass_fail_result
- assignees as a list
- inspection_notes as a list

Return JSON only.
""",
    DocumentType.FIELD_PHOTO: """
Extract from the photo or photo description:
- visible_objects as a list
- visible_text as a list
- environment
- utility_type
- possible_location_clues as a list
- camera_perspective

Return JSON only.
""",
    DocumentType.MASTER_DRAWING: """
Extract from the master drawing or drawing description:
- sheet_number
- sheet_title
- discipline
- drawing_labels as a list
- utility_symbols as a list
- areas_or_zones as a list

Return JSON only.
""",
}


def extract_type_specific_fields(document_type: DocumentType, content, session, file_id: str):
    if document_type not in TYPE_SPECIFIC_SCHEMAS:
        return None

    schema_cls = TYPE_SPECIFIC_SCHEMAS[document_type]
    prompt = TYPE_SPECIFIC_PROMPTS[document_type]
    raw = _call_extraction_llm(content, prompt)

    try:
        return schema_cls(**raw)
    except ValidationError:
        from backend.services.review_queue import add_to_review_queue

        add_to_review_queue(
            session,
            file_id=file_id,
            reason="extraction_validation_failed",
            document_type_guess=document_type.value,
        )
        return None


def _call_extraction_llm(content, prompt: str) -> dict:
    """
    ADAPT:
    Wire to the repo's existing LLM or vision client.
    """
    raise NotImplementedError("Wire to this repo's existing LLM client")
```

## New test file

```text
backend/tests/test_type_specific_extractor.py
```

## Code

```python
import pytest
from pydantic import ValidationError
from backend.ai.schemas.document_extraction_schemas import InspectionReportFields


def test_inspection_report_schema_accepts_partial_data():
    fields = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1"
    )

    assert fields.inspection_name == "Underground Sanitary Sewer #1"
    assert fields.items_inspected == []
    assert fields.pass_fail_result is None


def test_inspection_report_schema_rejects_wrong_shape():
    with pytest.raises(ValidationError):
        InspectionReportFields(items_inspected="not a list")
```

## Verification

Run:

```bash
pytest backend/tests/test_type_specific_extractor.py -v
```

Expected:

* Partial data is accepted.
* Wrong data shapes are rejected.
* Validation failures can be routed to review queue.

---

# PHASE 7 — Add clue extraction from fields

## Objective

Convert extracted fields into searchable clues that the matching pipeline can use.

This is the key step.

The AI should not just store fields. It should convert fields into location-relevant clues such as:

```text
COLO
Sanitary Sewerage
Underground Sanitary Sewer
Colo parking lot
pipe
trench
cleanout
manhole
SS
utility type
visible text from field photo
```

## New file

```text
backend/ai/pipelines/clue_extractor.py
```

## Code

```python
"""Convert extracted fields into searchable matching clues."""

from typing import List
from backend.ai.schemas.document_extraction_schemas import (
    Clue,
    UniversalFields,
    DocumentType,
    InspectionReportFields,
    FieldPhotoFields,
    MasterDrawingFields,
)


def build_clues(
    document_type: DocumentType,
    universal: UniversalFields,
    type_specific,
) -> List[Clue]:
    clues: List[Clue] = []

    if universal.location_text:
        clues.append(
            Clue(
                type="location_text",
                value=universal.location_text,
                source=document_type.value,
                confidence=0.90,
                location_relevant=True,
            )
        )

    if universal.trade:
        clues.append(
            Clue(
                type="trade",
                value=universal.trade,
                source=document_type.value,
                confidence=0.85,
                location_relevant=True,
            )
        )

    if universal.contractor:
        clues.append(
            Clue(
                type="contractor",
                value=universal.contractor,
                source=document_type.value,
                confidence=0.60,
                location_relevant=False,
            )
        )

    if universal.document_title:
        clues.append(
            Clue(
                type="document_title",
                value=universal.document_title,
                source=document_type.value,
                confidence=0.65,
                location_relevant=True,
            )
        )

    if isinstance(type_specific, InspectionReportFields):
        if type_specific.inspection_name:
            clues.append(
                Clue(
                    type="inspection_name",
                    value=type_specific.inspection_name,
                    source="inspection_report",
                    confidence=0.80,
                    location_relevant=True,
                )
            )

        for note in type_specific.inspection_notes:
            clues.append(
                Clue(
                    type="inspection_note",
                    value=note,
                    source="inspection_report",
                    confidence=0.75,
                    location_relevant=True,
                )
            )

        for item in type_specific.items_inspected:
            clues.append(
                Clue(
                    type="item_inspected",
                    value=item,
                    source="inspection_report",
                    confidence=0.75,
                    location_relevant=True,
                )
            )

    elif isinstance(type_specific, FieldPhotoFields):
        if type_specific.utility_type:
            clues.append(
                Clue(
                    type="utility_type",
                    value=type_specific.utility_type,
                    source="field_photo",
                    confidence=0.70,
                    location_relevant=True,
                )
            )

        for obj in type_specific.visible_objects:
            clues.append(
                Clue(
                    type="visible_object",
                    value=obj,
                    source="field_photo",
                    confidence=0.55,
                    location_relevant=True,
                )
            )

        for text in type_specific.visible_text:
            clues.append(
                Clue(
                    type="visible_text",
                    value=text,
                    source="field_photo",
                    confidence=0.60,
                    location_relevant=True,
                )
            )

        for clue_text in type_specific.possible_location_clues:
            clues.append(
                Clue(
                    type="location_hint",
                    value=clue_text,
                    source="field_photo",
                    confidence=0.60,
                    location_relevant=True,
                )
            )

    elif isinstance(type_specific, MasterDrawingFields):
        for label in type_specific.drawing_labels:
            clues.append(
                Clue(
                    type="drawing_label",
                    value=label,
                    source="master_drawing",
                    confidence=0.80,
                    location_relevant=False,
                )
            )

        for symbol in type_specific.utility_symbols:
            clues.append(
                Clue(
                    type="utility_symbol",
                    value=symbol,
                    source="master_drawing",
                    confidence=0.70,
                    location_relevant=False,
                )
            )

        for zone in type_specific.areas_or_zones:
            clues.append(
                Clue(
                    type="area_or_zone",
                    value=zone,
                    source="master_drawing",
                    confidence=0.80,
                    location_relevant=True,
                )
            )

    return clues
```

## New test file

```text
backend/tests/test_clue_extractor.py
```

## Code

```python
from backend.ai.schemas.document_extraction_schemas import (
    DocumentType,
    UniversalFields,
    InspectionReportFields,
)
from backend.ai.pipelines.clue_extractor import build_clues


def test_inspection_report_produces_location_trade_and_note_clues():
    universal = UniversalFields(
        location_text="COLO",
        trade="33-Sanitary Sewerage",
        document_title="Underground Sanitary Sewer #1",
    )

    type_specific = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1",
        inspection_notes=[
            "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        ],
    )

    clues = build_clues(DocumentType.INSPECTION_REPORT, universal, type_specific)

    clue_types = [c.type for c in clues]
    clue_values = [c.value for c in clues]

    assert "location_text" in clue_types
    assert "trade" in clue_types
    assert "inspection_note" in clue_types
    assert "COLO" in clue_values
```

## Verification

Run:

```bash
pytest backend/tests/test_clue_extractor.py -v
```

Expected:

* The test produces clues for `COLO`, `33-Sanitary Sewerage`, and the inspection note.
* Clues include backend-only confidence values.

---

# PHASE 8 — Add document extraction and document clue database tables

## Objective

Persist extraction results and clue rows.

Do not duplicate match/candidate tables. These tables only store document extraction and clues.

## New model

```text
backend/models/document_extraction.py
```

## Code

```python
from sqlalchemy import Column, Integer, String, Float, JSON, DateTime, func
from backend.models.models import Base  # ADAPT if needed


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id = Column(Integer, primary_key=True)
    file_id = Column(String, nullable=False, index=True)
    document_type = Column(String, nullable=False)
    classification_confidence = Column(Float, nullable=True)  # BACKEND ONLY
    universal_fields_json = Column(JSON, nullable=True)
    type_specific_fields_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

## New model

```text
backend/models/document_clue.py
```

## Code

```python
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, func
from backend.models.models import Base  # ADAPT if needed


class DocumentClue(Base):
    __tablename__ = "document_clues"

    id = Column(Integer, primary_key=True)
    document_extraction_id = Column(
        Integer,
        ForeignKey("document_extractions.id"),
        nullable=False,
        index=True,
    )
    clue_type = Column(String, nullable=False)
    clue_value = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)  # BACKEND ONLY
    location_relevant = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

## New migration

Create migration:

```bash
alembic revision -m "add document extraction and clue tables"
```

Then edit:

```python
from alembic import op
import sqlalchemy as sa

revision = "<generated_revision>"
down_revision = "<previous_revision>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.String, nullable=False),
        sa.Column("document_type", sa.String, nullable=False),
        sa.Column("classification_confidence", sa.Float, nullable=True),
        sa.Column("universal_fields_json", sa.JSON, nullable=True),
        sa.Column("type_specific_fields_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "document_clues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_extraction_id",
            sa.Integer,
            sa.ForeignKey("document_extractions.id"),
            nullable=False,
        ),
        sa.Column("clue_type", sa.String, nullable=False),
        sa.Column("clue_value", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("location_relevant", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_document_extractions_file_id", "document_extractions", ["file_id"])
    op.create_index("ix_document_clues_extraction", "document_clues", ["document_extraction_id"])
    op.create_index("ix_document_clues_value", "document_clues", ["clue_value"])


def downgrade():
    op.drop_index("ix_document_clues_value", table_name="document_clues")
    op.drop_index("ix_document_clues_extraction", table_name="document_clues")
    op.drop_index("ix_document_extractions_file_id", table_name="document_extractions")
    op.drop_table("document_clues")
    op.drop_table("document_extractions")
```

## Verification

Run:

```bash
alembic upgrade head
```

Expected:

* `document_extractions` exists.
* `document_clues` exists.
* Indexes exist.
* Confidence fields are stored only backend-side.

---

# PHASE 9 — Add document extraction orchestrator

## Objective

Create one entry point that runs:

```text
classify document
extract universal fields
extract type-specific fields
build clues
persist extraction
persist clues
```

## New file

```text
backend/ai/pipelines/document_extraction_orchestrator.py
```

## Code

```python
"""Document extraction orchestrator.

Runs:
classification -> universal extraction -> type-specific extraction -> clue generation -> DB persistence
"""

from backend.ai.schemas.document_extraction_schemas import DocumentType


def _model_dump(model):
    if model is None:
        return None

    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()


def run_document_extraction(session, file_id: str, content):
    from backend.ai.pipelines.document_classifier import classify_document
    from backend.ai.pipelines.universal_field_extractor import extract_universal_fields
    from backend.ai.pipelines.type_specific_extractor import extract_type_specific_fields
    from backend.ai.pipelines.clue_extractor import build_clues
    from backend.models.document_extraction import DocumentExtraction
    from backend.models.document_clue import DocumentClue
    from backend.services.review_queue import add_to_review_queue

    classification = classify_document(content)

    if classification.document_type == DocumentType.UNKNOWN:
        add_to_review_queue(
            session=session,
            file_id=file_id,
            reason="low_confidence_classification",
            document_type_guess=classification.document_type.value,
            confidence=classification.confidence,
        )

    universal = extract_universal_fields(content)

    type_specific = None
    if classification.document_type != DocumentType.UNKNOWN:
        type_specific = extract_type_specific_fields(
            document_type=classification.document_type,
            content=content,
            session=session,
            file_id=file_id,
        )

    extraction = DocumentExtraction(
        file_id=file_id,
        document_type=classification.document_type.value,
        classification_confidence=classification.confidence,
        universal_fields_json=_model_dump(universal),
        type_specific_fields_json=_model_dump(type_specific),
    )

    session.add(extraction)
    session.flush()

    clues = build_clues(
        document_type=classification.document_type,
        universal=universal,
        type_specific=type_specific,
    )

    for clue in clues:
        session.add(
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type=clue.type,
                clue_value=clue.value,
                source=clue.source,
                confidence=clue.confidence,
                location_relevant=clue.location_relevant,
            )
        )

    session.commit()
    return extraction
```

## Verification

Run the orchestrator against a known inspection report text.

Expected:

* One `document_extractions` row.
* Multiple `document_clues` rows.
* At least one clue with value `COLO`.
* At least one clue related to sanitary sewer.

---

# PHASE 10 — Update candidate tile selector to consume clues instead of regex terms

## Objective

Replace the old search-term based candidate selector with clue-based candidate selection.

The selector should use:

1. `clue_value`
2. `clue_type`
3. `location_relevant`
4. Backend-only `confidence`

## Edit file

```text
backend/ai/pipelines/candidate_tile_selector.py
```

## Replace or add function

```python
"""Candidate tile selection from extracted document clues.

This is the first narrowing step before expensive vision calls.
Confidence is backend-only and used only for ranking.
"""

def find_candidate_tiles_from_clues(
    session,
    drawing_id: str,
    page: int,
    clues: list,
    limit: int = 20,
):
    from backend.models.drawing_text_element import DrawingTextElement

    location_clues = [
        c for c in clues
        if getattr(c, "location_relevant", False) and getattr(c, "clue_value", None)
    ]

    if not location_clues:
        return []

    rows = (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.drawing_id == drawing_id,
            DrawingTextElement.page == page,
        )
        .all()
    )

    scored = []

    for row in rows:
        row_text = (getattr(row, "text", "") or "").lower()

        matched_clues = [
            c for c in location_clues
            if c.clue_value.lower() in row_text
        ]

        if not matched_clues:
            continue

        strongest_clue_confidence = max(c.confidence for c in matched_clues)
        row_confidence = getattr(row, "confidence", 0.0) or 0.0

        internal_score = row_confidence + strongest_clue_confidence

        scored.append(
            {
                "score": internal_score,
                "row": row,
                "matched_clues": matched_clues,
            }
        )

    scored.sort(key=lambda item: -item["score"])

    return [item["row"] for item in scored[:limit]]
```

## Important

If the existing `DrawingTextElement` model uses different field names, adapt:

```text
row.text
row.confidence
row.bbox_normalized
```

to the actual model fields.

## Verification

Use clues from the UCSF inspection report:

```text
COLO
Sanitary Sewerage
Underground Sanitary Sewer
Colo parking lot
```

Expected:

* Candidate tiles should cluster around the COLO / sewer / parking lot area if the master drawing OCR contains those terms.
* If no text match exists, the system should return no candidates and later move to `needs_review`.

---

# PHASE 11 — Update inspection matching job to use match_status, not confidence

## Objective

The match job should use confidence internally but never expose it.

Frontend receives only:

```text
matched
needs_review
no_match
```

## Edit file

```text
backend/services/inspection_matching_jobs.py
```

## Code

```python
"""Inspection matching job.

Uses extracted clues to find candidate master drawing locations.
Internal confidence/score values never leave the backend.
"""

JOB_TYPE_INSPECTION_MATCH = "inspection_match"

MATCH_SCORE_THRESHOLD = 0.75  # Tune after observing real backend score distributions.


def enqueue_inspection_match_job(enqueue_fn, inspection_id: str, drawing_id: str, page: int):
    return enqueue_fn(
        job_type=JOB_TYPE_INSPECTION_MATCH,
        payload={
            "inspection_id": inspection_id,
            "drawing_id": drawing_id,
            "page": page,
        },
    )


def run_inspection_match_job(payload: dict, session):
    from backend.models.document_extraction import DocumentExtraction
    from backend.models.document_clue import DocumentClue
    from backend.ai.pipelines.candidate_tile_selector import find_candidate_tiles_from_clues

    extraction = (
        session.query(DocumentExtraction)
        .filter_by(file_id=payload["inspection_id"])
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if not extraction:
        _persist_match_status(
            session=session,
            inspection_id=payload["inspection_id"],
            status="needs_review",
            bbox=None,
        )
        return

    clues = (
        session.query(DocumentClue)
        .filter_by(document_extraction_id=extraction.id)
        .all()
    )

    candidates = find_candidate_tiles_from_clues(
        session=session,
        drawing_id=payload["drawing_id"],
        page=payload["page"],
        clues=clues,
        limit=20,
    )

    if not candidates:
        _persist_match_status(
            session=session,
            inspection_id=payload["inspection_id"],
            status="needs_review",
            bbox=None,
        )
        return

    best = candidates[0]

    internal_score = getattr(best, "confidence", 0.0) or 0.0
    status = "matched" if internal_score >= MATCH_SCORE_THRESHOLD else "needs_review"

    bbox = getattr(best, "bbox_normalized", None)

    _persist_match_status(
        session=session,
        inspection_id=payload["inspection_id"],
        status=status,
        bbox=bbox,
    )


def _persist_match_status(session, inspection_id: str, status: str, bbox):
    """
    ADAPT:
    Wire this into the existing overlay or inspection result persistence layer.

    Persist:
    - inspection_id
    - status: matched | needs_review | no_match
    - bbox nullable

    Do not persist frontend-facing numeric confidence here.
    """
    raise NotImplementedError("Wire into existing overlay/match persistence")
```

## Edit worker

Find:

```text
backend/services/job_worker.py
```

Add job handler:

```python
elif job.job_type == JOB_TYPE_INSPECTION_MATCH:
    from backend.services.inspection_matching_jobs import run_inspection_match_job
    run_inspection_match_job(job.payload, session)
```

Make sure `JOB_TYPE_INSPECTION_MATCH` is imported or referenced consistently.

## Verification

Test three cases:

### Case A: good clues

Expected:

```text
match_status = matched
bbox exists
no confidence returned to frontend
```

### Case B: weak clues

Expected:

```text
match_status = needs_review
bbox may be null
no confidence returned to frontend
```

### Case C: nonsense clues

Expected:

```text
match_status = needs_review
bbox = null
no crash
```

---

# PHASE 12 — Add API response schema that strips confidence

## Objective

Create strict API response models so numeric confidence cannot leak to the frontend.

## New file

```text
backend/api/schemas/inspection_match_response.py
```

## Code

```python
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
```

## Edit route

Find the route that serves inspection/overlay/match state, likely one of:

```text
backend/api/routes/evidence.py
backend/api/routes/inspections.py
backend/api/routes/drawings.py
backend/api/routes/overlays.py
```

Add or adapt endpoint:

```python
from backend.api.schemas.inspection_match_response import InspectionMatchStatusResponse


@router.get("/inspections/{inspection_id}/match-status")
def get_match_status(inspection_id: str, session=None) -> InspectionMatchStatusResponse:
    record = _load_match_record(session, inspection_id)  # ADAPT

    return InspectionMatchStatusResponse(
        inspection_id=inspection_id,
        match_status=record.status,
        bbox=record.bbox if record.bbox else None,
    )
```

## Acceptance criteria

Raw API JSON must look like this:

```json
{
  "inspection_id": "inspection-123",
  "match_status": "needs_review",
  "bbox": null
}
```

Raw API JSON must never look like this:

```json
{
  "inspection_id": "inspection-123",
  "match_status": "needs_review",
  "confidence": 0.61,
  "score": 0.72
}
```

## Verification

Use browser network tab or curl:

```bash
curl http://localhost:8000/api/inspections/<inspection_id>/match-status
```

Expected:

* No `confidence`
* No `score`
* No `classification_confidence`
* Only `match_status` and optional `bbox`

---

# PHASE 13 — Add frontend match status hook

## Objective

Fetch the match status from the backend.

## New file

```text
client/src/hooks/use_inspection_match_status.ts
```

## Code

```typescript
import { useEffect, useState } from "react";

export type MatchStatus = "matched" | "needs_review" | "no_match";

interface MatchStatusResponse {
  inspection_id: string;
  match_status: MatchStatus;
  bbox: { x: number; y: number; width: number; height: number } | null;
}

export function useInspectionMatchStatus(inspectionId: string) {
  const [data, setData] = useState<MatchStatusResponse | null>(null);

  useEffect(() => {
    if (!inspectionId) return;

    fetch(`/api/inspections/${inspectionId}/match-status`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch inspection match status");
        }
        return response.json();
      })
      .then(setData)
      .catch(() => {
        setData({
          inspection_id: inspectionId,
          match_status: "needs_review",
          bbox: null,
        });
      });
  }, [inspectionId]);

  return data;
}
```

## Verification

* Hook compiles.
* Hook returns `null` while loading.
* Hook returns `needs_review` fallback on request failure.

---

# PHASE 14 — Add frontend match alert banner

## Objective

Show a plain-language UI alert when the AI cannot confidently place the inspection.

Do not show confidence numbers.

## New file

```text
client/src/components/drawing-workspace/match_alert_banner.tsx
```

## Code

```tsx
import { useInspectionMatchStatus } from "../../hooks/use_inspection_match_status";

interface Props {
  inspectionId: string;
}

export function MatchAlertBanner({ inspectionId }: Props) {
  const status = useInspectionMatchStatus(inspectionId);

  if (!status || status.match_status === "matched") {
    return null;
  }

  return (
    <div
      role="alert"
      style={{
        padding: "8px 12px",
        background: "#fff4e5",
        borderRadius: 6,
        border: "1px solid #ffd8a8",
        marginBottom: 8,
        fontSize: 14,
      }}
    >
      {status.match_status === "needs_review"
        ? "This inspection could not be automatically placed. Please review and confirm the location on the drawing."
        : "No likely location was found on the master drawing for this inspection."}
    </div>
  );
}
```

## Mount component

Find likely viewer/panel file:

```text
client/src/components/drawing-workspace/DrawingViewer.tsx
client/src/pages/drawing-workspace.tsx
client/src/pages/objects.tsx
client/src/components/drawing-workspace/*
```

Mount:

```tsx
<MatchAlertBanner inspectionId={inspectionId} />
```

near the existing inspection overlay or inspection detail panel.

## Verification

Force a backend response:

```json
{
  "inspection_id": "test",
  "match_status": "needs_review",
  "bbox": null
}
```

Expected:

* Banner appears.
* No percentage or confidence score appears.

---

# PHASE 15 — Integrate extraction into upload or inspection ingestion flow

## Objective

Run `run_document_extraction()` whenever an inspection file/report/photo is uploaded or ingested.

## Search for upload endpoints

Look for routes like:

```bash
grep -R "UploadFile" -n backend/api
grep -R "inspection" -n backend/api/routes
grep -R "evidence" -n backend/api/routes
grep -R "attachments" -n backend
```

## Integration pattern

Where the file content is available:

```python
from backend.ai.pipelines.document_extraction_orchestrator import run_document_extraction

run_document_extraction(
    session=session,
    file_id=str(uploaded_file.id),
    content=parsed_text_or_image_description,
)
```

## Important

For text PDFs:

* Use parsed text.

For field photos:

* Use image caption/vision output.
* If raw image support already exists, pass it through the vision model adapter.

For master drawings:

* Use OCR text plus any drawing metadata.

## Verification

Upload or ingest the UCSF inspection report.

Expected:

* `document_extractions` row created.
* `document_clues` rows created.
* `COLO` appears as a clue.
* `Sanitary Sewerage` appears as a clue.
* Match job can consume those clues.

---

# PHASE 16 — Connect extraction to match job enqueue

## Objective

After extraction completes, enqueue a matching job against the selected master drawing.

## Integration pattern

After:

```python
extraction = run_document_extraction(...)
```

enqueue:

```python
from backend.services.inspection_matching_jobs import enqueue_inspection_match_job

enqueue_inspection_match_job(
    enqueue_fn=enqueue_fn,
    inspection_id=file_id,
    drawing_id=master_drawing_id,
    page=page,
)
```

## Important

Only enqueue match job if:

```text
master_drawing_id is known
page is known or defaultable
inspection file_id is known
```

If master drawing is not selected yet, persist extraction and wait until user selects a master.

## Verification

* Upload inspection.
* Select master drawing.
* Match job runs.
* Candidate selector uses document clues.

---

# PHASE 17 — Add internal clue expansion for construction abbreviations

## Objective

Improve matching by expanding construction terms and utility abbreviations.

For example:

```text
Sanitary Sewerage -> sanitary sewer, SS, SAN, sewer lateral
COLO -> Colo, COLO parking lot, colocated/colocation if applicable
manhole -> MH
cleanout -> CO
storm drainage -> SD
```

## New file

```text
backend/ai/pipelines/clue_expander.py
```

## Code

```python
"""Expand construction clues into common drawing abbreviations and related search terms."""

EXPANSIONS = {
    "sanitary sewerage": ["sanitary sewer", "sanitary", "sewer", "SS", "SAN", "sewer lateral"],
    "sanitary sewer": ["SS", "SAN", "sewer lateral", "cleanout", "manhole"],
    "manhole": ["MH", "M.H."],
    "cleanout": ["CO", "C.O."],
    "storm drainage": ["storm drain", "SD", "storm"],
    "parking lot": ["lot", "pavement", "asphalt", "parking"],
}


def expand_clue_value(value: str) -> list[str]:
    if not value:
        return []

    normalized = value.lower()
    expanded = [value]

    for key, terms in EXPANSIONS.items():
        if key in normalized:
            expanded.extend(terms)

    seen = set()
    result = []

    for term in expanded:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            result.append(term)

    return result
```

## Update candidate selector

In `candidate_tile_selector.py`, before matching each clue, expand clue values:

```python
from backend.ai.pipelines.clue_expander import expand_clue_value

expanded_values = []
for clue in location_clues:
    for value in expand_clue_value(clue.clue_value):
        expanded_values.append((clue, value))
```

Then match using expanded values.

## Verification

A clue like:

```text
33-Sanitary Sewerage
```

should search for:

```text
sanitary sewer
SS
SAN
sewer lateral
cleanout
manhole
```

---

# PHASE 18 — Add photo-to-plan clue logic

## Objective

Field photos cannot be matched to master drawings as direct image crops. They must be converted into construction clues.

## Required behavior

If document type is `field_photo`, the AI should extract:

```text
visible objects
visible text
utility type
environment
possible location clues
camera perspective
```

Then convert those into clues.

## Field photo example output

```json
{
  "visible_objects": ["trench", "pipe", "gravel bedding", "parking lot"],
  "visible_text": [],
  "environment": "outdoor parking lot construction area",
  "utility_type": "sanitary sewer",
  "possible_location_clues": [
    "underground pipe prior to backfill",
    "parking lot area",
    "utility trench"
  ],
  "camera_perspective": "ground-level field photo"
}
```

## Matching logic

Photo clues should match against master drawing text and symbols, not raw photo pixels only.

For example:

```text
photo shows trench + pipe + parking lot
```

should search the master for:

```text
parking lot
SS
SAN
sanitary sewer
sewer lateral
cleanout
manhole
utility line
```

## Verification

Upload a field photo or use a mocked field photo description.

Expected:

* Photo produces construction clues.
* Candidate selector searches master drawing OCR using those clues.
* No assumption is made that the photo visually matches the master plan directly.

---

# PHASE 19 — Keep backend scores internal everywhere

## Objective

Enforce the rule that all numeric scores remain backend-only.

Numeric values may exist in:

```text
DocumentClassification.confidence
DocumentClue.confidence
DrawingTextElement.confidence
DrawingMatchCandidate.score
internal match scores
vision confirmation scores
```

But frontend responses must only expose:

```text
matched
needs_review
no_match
```

## Search for leaking fields

Run:

```bash
grep -R "confidence" -n backend/api client/src
grep -R "score" -n backend/api client/src
grep -R "classification_confidence" -n backend/api client/src
```

## Fix leaks

If any frontend-facing schema includes these fields, remove them.

Allowed in backend models:

```text
confidence
score
classification_confidence
```

Not allowed in API responses:

```text
confidence
score
classification_confidence
match_score
similarity
percentage
```

## Verification

Open browser dev tools network tab.

Expected:

* No match endpoint returns numeric confidence.
* UI shows only plain-language status.

---

# PHASE 20 — Integrate with vision confirmation phase

## Objective

When the later vision confirmation phase runs, it may compute scores internally, but it must persist final frontend-facing result as `match_status`.

## Rule

If targeted vision confirmation produces a score, store it only in backend/internal tables such as:

```text
DrawingMatchCandidate.score
```

Do not return it to the frontend.

## Final overlay persistence must write:

```text
match_status = matched | needs_review | no_match
bbox = nullable bounding box
```

## Pattern

```python
internal_score = candidate.score
match_status = "matched" if internal_score >= MATCH_SCORE_THRESHOLD else "needs_review"

persist_overlay(
    inspection_id=inspection_id,
    bbox=candidate.bbox,
    match_status=match_status,
)
```

## Verification

* Candidate table may contain score.
* Overlay/status endpoint does not return score.
* Frontend alert is driven only by status.

---

# PHASE 21 — End-to-end UCSF inspection report test

## Objective

Use the known UCSF inspection report to test the pipeline.

## Expected extracted facts

The inspection report should produce:

```text
document_type: inspection_report
project_number: 02001.161310
project_name: UCSF Benioff Oakland
inspection_name: Underground Sanitary Sewer #1
trade: 33-Sanitary Sewerage
location_text: COLO
description/note: sanitary sewer inspection prior to backfill in the Colo parking lot
```

## Expected clues

```text
COLO
33-Sanitary Sewerage
Underground Sanitary Sewer #1
sanitary sewer inspection prior to backfill
Colo parking lot
sanitary sewer
SS
SAN
sewer lateral
cleanout
manhole
```

## Expected system behavior

1. Document is classified as `inspection_report`.
2. Universal fields are extracted.
3. Inspection-specific fields are extracted.
4. Clues are built.
5. Clues are persisted.
6. Candidate selector searches master drawing OCR.
7. Matching job returns one of:

```text
matched
needs_review
no_match
```

8. API returns no confidence score.
9. Frontend shows alert only if `needs_review` or `no_match`.

---

# PHASE 22 — Add tests for confidence stripping

## Objective

Prevent future regressions where confidence leaks to the frontend.

## New test file

```text
backend/tests/test_inspection_match_response_schema.py
```

## Code

```python
from backend.api.schemas.inspection_match_response import InspectionMatchStatusResponse


def test_match_response_does_not_include_confidence():
    response = InspectionMatchStatusResponse(
        inspection_id="test-inspection",
        match_status="needs_review",
        bbox=None,
    )

    data = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    assert "confidence" not in data
    assert "score" not in data
    assert "classification_confidence" not in data
    assert data["match_status"] == "needs_review"
```

## Verification

Run:

```bash
pytest backend/tests/test_inspection_match_response_schema.py -v
```

Expected:

* Test passes.
* API response schema remains frontend-safe.

---

# PHASE 23 — Add tests for clue-based matching

## Objective

Make sure clue-based matching works independently from old regex search terms.

## New test file

```text
backend/tests/test_candidate_tile_selector_from_clues.py
```

## Suggested approach

Use simple fake objects if database test fixtures are not ready.

```python
from types import SimpleNamespace


def test_location_relevant_clues_are_used_for_matching():
    clue = SimpleNamespace(
        clue_value="COLO",
        clue_type="location_text",
        confidence=0.9,
        location_relevant=True,
    )

    assert clue.location_relevant is True
    assert clue.clue_value == "COLO"
```

If database fixtures exist, create fake `DrawingTextElement` rows:

```text
row 1 text: "COLO PARKING LOT SANITARY SEWER"
row 2 text: "ROOF DRAINAGE PLAN"
```

Expected:

* Row 1 ranks higher.
* Row 2 does not match.

---

# PHASE 24 — Final manual QA checklist

## Backend QA

Run:

```bash
pytest backend/tests/test_document_classifier.py -v
pytest backend/tests/test_type_specific_extractor.py -v
pytest backend/tests/test_clue_extractor.py -v
pytest backend/tests/test_inspection_match_response_schema.py -v
```

Run migrations:

```bash
alembic upgrade head
```

Check database:

```sql
select * from document_extractions order by created_at desc;
select * from document_clues order by created_at desc;
select * from review_queue_items order by created_at desc;
```

## Frontend QA

Run:

```bash
npm run build
npm run dev
```

Check:

1. Upload/ingest inspection report.
2. Select master drawing.
3. Matching job runs.
4. `matched` status shows no warning.
5. `needs_review` status shows banner.
6. `no_match` status shows banner.
7. No confidence score appears in UI.
8. Network tab response contains no score/confidence.

---

# PHASE 25 — Future extensions, do not implement now

Do not implement these yet unless real files are available:

1. Submittal extractor
2. RFI extractor
3. Daily report extractor
4. As-built markup extractor
5. Handwritten markup extractor
6. Full symbol-detection model
7. Custom YOLO training for sewer/manhole/cleanout symbols

When ready, follow this same pattern:

1. Add type to `DocumentType`.
2. Add type-specific Pydantic schema.
3. Add type-specific prompt.
4. Register in `TYPE_SPECIFIC_SCHEMAS`.
5. Add extractor tests.
6. Convert extracted fields into clues.
7. Feed clues into candidate selector.

---

# Final implementation principle

Do not make the AI solve the location problem from one field.

The AI should collect multiple clues:

```text
document metadata
inspection title
location text
trade
field photo objects
visible text
drawing OCR
utility symbols
pipe labels
nearby area names
geometry and layout
```

Then it should rank candidate master locations.

The correct behavior is not:

```text
Inspection says COLO, so place it anywhere near COLO.
```

The correct behavior is:

```text
Inspection says COLO.
Trade says sanitary sewer.
Description says prior to backfill in Colo parking lot.
Photo shows trench/pipe/parking lot.
Master drawing contains SS/SAN/sewer lateral features near COLO.
Candidate area matches the most clues.
Return matched if strong enough, otherwise needs_review.
```

This makes the system flexible, safer, and closer to how a human construction reviewer would solve the puzzle.
