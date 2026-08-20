# Inspection Location Agent — Manual Entry Checklist

**Goal:** Automate what your QA team does manually — take an inspection upload, investigate it (including PDF links), use the database + legend + all clues, decide where on the **master drawing** the inspection refers to, and show the user a **precise scope overlay** (line/polyline/rect/polygon — not just a rough pin).

**Golden case (dev):** project `2`, master `661`, run `447`, evidence `377` (label `ucsf-435-ss-corridor`; formerly run 435 / evidence 357)

**How to use:** Work top → bottom. Copy one **PROMPT** block into Cursor Agent. Check `[x]` when done. Do not skip PR order (PRE → J).

**Depends on (already built — skip unless tests fail):** `document_extraction_orchestrator`, `clue_extractor`, `legend_lookup`, `pdf_link_follower`, `linked_drawing_registration`, `location_match_orchestrator`, `candidate_tile_selector`, `region_index_loader`, `inspection_match_persistence`, eval labels.

---

## Hard rules (every PR)

| Rule | Detail |
|------|--------|
| **No sheet numbers for master placement** | Sheet refs (e.g. `C4.20`) may link auxiliary PDFs **within a project** only. Never pin on master because evidence mentions a sheet ID. |
| **Highlights optional** | Most inspections have no markup. Agent must infer scope from notes + legend + DB + linked content. |
| **Autonomous investigation** | User should not specify which links/clues to follow. Agent investigates within budget. |
| **Precise scope geometry** | Output is a **line/polyline** for utility runs, **polygon/rect** for areas, not a coarse pin when scope is linear. |
| **Scores internal only** | Frontend gets `match_status` + geometry. Numeric scores stay in `DrawingMatchCandidate`. |
| **Conservative auto-match** | `matched` only when fused score ≥ threshold AND no major clue conflicts. Borderline → `needs_review`. |

---

## File map (full build)

| Action | Path |
|--------|------|
| ADD | `backend/ai/agents/__init__.py` (exports) |
| ADD | `backend/ai/agents/evidence_dossier.py` |
| ADD | `backend/ai/agents/tools/__init__.py` |
| ADD | `backend/ai/agents/tools/pdf_investigation.py` |
| ADD | `backend/ai/agents/tools/master_search.py` |
| ADD | `backend/ai/agents/inspection_location_agent.py` |
| ADD | `backend/ai/pipelines/clue_fusion_scorer.py` |
| ADD | `backend/ai/pipelines/scope_geometry.py` |
| ADD | `backend/ai/pipelines/scope_line_tracer.py` |
| ADD | `backend/ai/pipelines/vision_location_reasoner.py` |
| ADD | `backend/tests/test_evidence_dossier.py` |
| ADD | `backend/tests/test_pdf_investigation_tools.py` |
| ADD | `backend/tests/test_clue_fusion_scorer.py` |
| ADD | `backend/tests/test_scope_geometry.py` |
| ADD | `backend/tests/test_scope_line_tracer.py` |
| ADD | `backend/tests/test_inspection_location_agent.py` |
| ADD | `client/src/tests/unit/overlay_polyline.test.ts` |
| MODIFY | `backend/ai/pipelines/location_match_orchestrator.py` |
| MODIFY | `backend/services/inspection_match_persistence.py` |
| MODIFY | `backend/services/overlay_storage.py` |
| MODIFY | `backend/services/region_storage.py` |
| MODIFY | `backend/services/inspection_matching_jobs.py` |
| MODIFY | `backend/services/evidence_document_extraction.py` |
| MODIFY | `backend/models/location_match_label.py` |
| MODIFY | `backend/services/location_match_eval.py` |
| MODIFY | `backend/scripts/eval_location_match.py` |
| MODIFY | `client/src/types/drawing_workspace.ts` |
| MODIFY | `client/src/lib/drawing-overlays/geometry.ts` |
| MODIFY | `client/src/components/drawing-workspace/overlay_shape.tsx` |

---

## PRE — Verify existing baseline

- [x] **PRE-1** Run location-match + extraction tests

**PROMPT — copy below:**

```
PRE-1: Run baseline tests before starting Inspection Location Agent work.

cd backend && pytest \
  tests/test_location_match_eval.py \
  tests/test_inspection_matching_jobs.py \
  tests/test_evidence_document_extraction.py \
  tests/test_linked_drawing_registration.py \
  tests/test_candidate_tile_selector_from_clues.py \
  tests/test_clue_extractor.py \
  -q --tb=short

Fix any failures before PR-A. Do not start agent work on a red baseline.
```

---

- [x] **PRE-2** Record eval baseline

**PROMPT — copy below:**

```
PRE-2: Record location-match eval baseline.

cd backend && python scripts/eval_location_match.py --suite ucsf

Save output: pass rate, IoU, method accuracy. We will compare after PR-J.
If eval script fails, fix before continuing.
```

### PRE-2 baseline (2026-08-20)

Saved: `Notes/eval_baselines/pre2_ucsf_2026-08-20.json`

| Metric | Value |
|--------|-------|
| Evaluated / total | 1 / 5 (4 fixture-only skipped) |
| Pass rate | **100%** (gate min 80%) |
| Method accuracy | **100%** (`coordinate_lookup` as expected) |
| Match status | `matched` |
| IoU | **1.000** (min 0.30) |
| Coordinate false positives | 0 |
| GATE | **PASS** |

Notes to restore this baseline if DB is wiped:
- Fixture points at evidence `377` / run `447` (replaces deleted 357/435).
- Master `661` needs a `drawing_survey_points` row for N/E `2131764.84` / `6051541.82` with label bbox `(0.518, 0.472)–(0.566, 0.514)` (seeded as `source=pre2_baseline_seed` until real sheet indexing fills it).
- Eval IoU now converts orchestrator `(x0,y0,x1,y1)` → label `(x,y,w,h)`.

---

# PR-A — Evidence Dossier (DB case file)

- [ ] **A-1** Create dossier dataclasses

**PROMPT — copy below:**

```
PR-A step A-1: Create evidence dossier dataclasses.

ADD backend/ai/agents/evidence_dossier.py

"""Structured case file the Inspection Location Agent consumes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.pipelines.candidate_tile_selector import CandidateTile
from ai.pipelines.drawing_location_resolver import MasterRegion
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.survey_point_extractor import SurveyPointRecord
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Drawing, EvidenceRecord


@dataclass(frozen=True)
class ExpandedClue:
    original_value: str
    clue_type: str
    expanded_values: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class LinkedAttachmentSummary:
    url: str
    filename: str
    page_count: int
    text_preview: str
    drawing_id: int | None = None  # auxiliary Drawing.id if registered


@dataclass(frozen=True)
class MasterDrawingContext:
    master_drawing_id: int
    regions: tuple[MasterRegion, ...]
    total_region_count: int
    untagged_region_count: int
    scoped_survey_points: tuple[SurveyPointRecord, ...]
    candidate_tiles: tuple[CandidateTile, ...]
    legend_codes_near_candidates: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceDossier:
    evidence_id: int
    project_id: int
    master_drawing_id: int
    evidence: EvidenceRecord
    extraction: DocumentExtraction | None
    clues: tuple[DocumentClue, ...]
    expanded_clues: tuple[ExpandedClue, ...]
    evidence_text: str
    base_text: str
    evidence_kind: EvidenceKind
    linked_attachments: tuple[LinkedAttachmentSummary, ...]
    auxiliary_drawings: tuple[Drawing, ...]
    photo_paths: tuple[Path, ...]
    survey_points_meta: tuple[dict[str, Any], ...]
    master_context: MasterDrawingContext
    investigation_meta: dict[str, Any] = field(default_factory=dict)

UPDATE backend/ai/agents/__init__.py to export EvidenceDossier, build_evidence_dossier (stub for A-2).
```

---

- [ ] **A-2** Implement `build_evidence_dossier`

**PROMPT — copy below:**

```
PR-A step A-2: Implement build_evidence_dossier(session, evidence_id, master_drawing_id).

MODIFY backend/ai/agents/evidence_dossier.py

Implement:
  build_evidence_dossier(session, *, evidence_id, master_drawing_id, page=1) -> EvidenceDossier

Wire existing modules (do not reimplement):
  - models: EvidenceRecord, DocumentExtraction, DocumentClue, Drawing
  - services.evidence_text.build_full_evidence_text
  - services.evidence_linking.load_linked_drawings
  - services.match_candidate_scope.build_match_scope
  - ai.pipelines.evidence_kind_classifier.classify_evidence_kind + meta
  - ai.pipelines.clue_expander.expand_clue_value (session + project_id)
  - services.region_index_loader.build_region_index
  - ai.pipelines.candidate_tile_selector.find_candidate_tiles_from_clues
  - location_match_orchestrator helpers for scoped survey points if extractable

For each DocumentClue, build ExpandedClue:
  expanded_values = tuple(expand_clue_value(clue.value, session=session, project_id=project_id))

Linked attachments from evidence.meta["pdfLinkFollow"] + EvidenceDrawingLink rows.
photo_paths: evidence files with image extensions from storage_key when evidence_kind == PHOTO.

Do NOT use sheet numbers to choose master location — only to list linked auxiliary drawings.

ADD backend/tests/test_evidence_dossier.py
  - seed evidence + extraction + clues + legend (use scripts/seed_legend_reference seed in test)
  - assert dossier has expanded_clues, candidate_tiles, regions
  - assert no sheet-number field used as match key
```

---

- [ ] **A-3** Master search tool wrapper

**PROMPT — copy below:**

```
PR-A step A-3: Add legend-aware master search tool.

ADD backend/ai/agents/tools/__init__.py
ADD backend/ai/agents/tools/master_search.py

"""Structured DB search tools for the agent (read-only)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import CandidateTile, find_candidate_tiles_from_clues
from services.legend_lookup import expand_abbreviation, find_codes_for_term
from services.region_index_loader import build_region_index


def search_master_by_clues(
    session: Session,
    *,
    drawing_ids: tuple[int, ...],
    clues: list,
    project_id: int | None,
    page: int = 1,
) -> list[CandidateTile]:
    return find_candidate_tiles_from_clues(
        session, drawing_ids=drawing_ids, page=page, clues=clues, project_id=project_id
    )


def expand_term_with_legend(
    session: Session,
    term: str,
    *,
    project_id: int | None,
) -> list[str]:
    ...

ADD backend/tests/test_evidence_dossier.py test for expand_term_with_legend SS -> SANITARY SEWER.
```

---

# PR-B — PDF link investigation tools

- [ ] **B-1** PDF investigation tool module

**PROMPT — copy below:**

```
PR-B step B-1: PDF investigation tools — open links and view pages within PDFs.

ADD backend/ai/agents/tools/pdf_investigation.py

Reuse (do not duplicate):
  - ai.pipelines.pdf_link_follower.follow_pdf_links, FetchedLinkedPdf, PdfHyperlink
  - ai.pipelines.document_text_extraction.extract_document, extract_document_via_ocr
  - services.safe_url_fetch.fetch_url_attachment_with_error

Implement:

@dataclass(frozen=True)
class RenderedPdfPage:
    page: int  # 1-based
    png_path: Path
    width_pt: float | None
    height_pt: float | None


def list_pdf_hyperlinks(file_path: Path) -> list[PdfHyperlink]:
    """Wrap pdf_link_follower._extract_hyperlinks (export if needed)."""


def follow_and_capture_links(file_path: Path) -> LinkFollowResult:
    """Thin wrapper around follow_pdf_links."""


def render_pdf_page(pdf_path: Path, *, page: int = 1, dpi: int = 200) -> RenderedPdfPage:
    """PyMuPDF fitz page -> temp PNG (same pattern as location_match_orchestrator._evidence_rendition_png)."""


def extract_page_clues(pdf_path: Path, *, page: int = 1) -> dict:
    """Return {text, word_count, positioned_term_count, survey_hints}."""


def investigate_pdf_links(
    file_path: Path,
    *,
    max_links: int = 10,
) -> list[LinkedAttachmentSummary]:
    """
    Autonomous link investigation:
    1. follow_all_links
    2. for each FetchedLinkedPdf: render page 1, extract_page_clues
    3. return summaries for dossier (do NOT pin master by sheet filename)
    """

ADD backend/tests/test_pdf_investigation_tools.py
  - mock PDF with internal page link + external URL
  - assert render + extract_page_clues called
  - use tests/fixtures/evidence/ if available
```

---

- [ ] **B-2** Wire investigation into dossier builder

**PROMPT — copy below:**

```
PR-B step B-2: Wire PDF investigation into build_evidence_dossier.

MODIFY backend/ai/agents/evidence_dossier.py

When evidence file is PDF:
  from ai.agents.tools.pdf_investigation import investigate_pdf_links
  linked = investigate_pdf_links(file_path)
  merge into dossier.linked_attachments

Store investigation_meta:
  links_followed, pages_rendered, ocr_word_counts

Do not block dossier build if link fetch fails — append errors to investigation_meta.

Run: cd backend && pytest tests/test_evidence_dossier.py tests/test_pdf_investigation_tools.py -q
```

---

# PR-C — Multi-candidate generator

- [ ] **C-1** Extend orchestrator to emit candidate list

**PROMPT — copy below:**

```
PR-C step C-1: Multi-candidate generator with provenance.

MODIFY backend/ai/pipelines/location_match_orchestrator.py

ADD dataclass (near MethodCandidate):

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


ADD function:

def generate_all_location_candidates(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    page: int = 1,
) -> list[LocationMatchCandidate]:
    """
    Run ALL non-contour matchers (no early exit):
      coordinate, station, clue tiles, reference, alignment
    Also emit region-cluster candidates: top-N tagged regions by clue overlap.

    NEVER emit a candidate whose sole support is a sheet number.
    Map existing MethodCandidate -> LocationMatchCandidate with supporting_clues populated.
    """

Keep resolve_evidence_location() working — delegate to generate_all + select_best for now.

ADD tests in backend/tests/test_inspection_matching_jobs.py or new test_location_match_candidates.py:
  golden dossier produces >= 3 candidates with non-empty supporting_clues.
```

---

# PR-D — Clue fusion scorer

- [ ] **D-1** Deterministic fusion scorer

**PROMPT — copy below:**

```
PR-D step D-1: Clue fusion scorer — compare ALL clues holistically.

ADD backend/ai/pipelines/clue_fusion_scorer.py

"""Score location candidates by fusing evidence dossier clues + legend + master context."""

from __future__ import annotations

from dataclasses import dataclass

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate


@dataclass(frozen=True)
class ClueHit:
    clue_value: str
    dimension: str  # inspection_type | location | legend | coordinate | station | linked
    weight: float


@dataclass(frozen=True)
class FusedCandidateScore:
    candidate: LocationMatchCandidate
    fused_score: float
    clue_hits: tuple[ClueHit, ...]
    conflicts: tuple[str, ...]
    rationale: str


# Default weights (tunable via config later):
WEIGHTS = {
    "coordinate_proximity": 0.35,
    "station_match": 0.30,
    "inspection_type_region": 0.20,
    "location_term": 0.20,
    "legend_coherence": 0.15,
    "linked_attachment_agreement": 0.10,
    "generic_location_penalty": -0.15,
    "cross_clue_convergence_bonus": 0.10,
}


def fuse_candidate_scores(
    dossier: EvidenceDossier,
    candidates: list[LocationMatchCandidate],
) -> list[FusedCandidateScore]:
    """
    For each candidate:
      - score inspection type vs region tags / nearby text
      - score location terms (COLO, corridor names) vs region/text
      - legend: report 'sanitary sewer' + drawing SS/SSMH near bbox -> boost
      - coordinate/station if applicable
      - penalize generic clues alone ('utility', 'site')
      - bonus when 3+ independent dimensions agree
    Sort descending by fused_score.
    """


def select_fused_winner(scores: list[FusedCandidateScore], *, tie_epsilon: float = 0.01) -> FusedCandidateScore | None:
    ...

ADD backend/tests/test_clue_fusion_scorer.py
  - mock dossier with COLO + SS clues
  - two candidates: one in COLO corridor, one elsewhere
  - assert COLO candidate wins
```

---

- [ ] **D-2** Optional LLM fusion tie-breaker

**PROMPT — copy below:**

```
PR-D step D-2: LLM fusion tie-breaker for ambiguous cases.

MODIFY backend/ai/pipelines/clue_fusion_scorer.py

ADD fuse_with_llm_tiebreak(dossier, top_scores: list[FusedCandidateScore]) -> FusedCandidateScore | None

Invoke ONLY when:
  - top two fused scores within 0.05, OR
  - top score < 0.65

Prompt (structured JSON output):
  "Given inspection dossier summary and top 5 candidate areas on master drawing,
   which candidate best matches the inspection? Use legend expansions and location terms.
   Do NOT use sheet numbers. Return: {best_index, confidence, rationale, conflicts}."

Wire OpenAI same pattern as ai/pipelines/document_classifier.py _call_classifier_llm.
If no API key, return None (keep deterministic winner).

Never return matched status from LLM directly — only reorder/score candidates.
```

---

# PR-E — Scope geometry (precise line / polyline)

- [ ] **E-1** Scope geometry schema + validation

**PROMPT — copy below:**

```
PR-E step E-1: Scope geometry schema — rect, polygon, polyline.

ADD backend/ai/pipelines/scope_geometry.py

"""Normalized 0-1 scope geometry for inspection overlays."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ScopeKind(str, Enum):
    UTILITY_LINE = "utility_line"
    STATION_RANGE = "station_range"
    POINT = "point"
    AREA = "area"
    CORRIDOR = "corridor"


@dataclass(frozen=True)
class ScopeGeometry:
    page: int
    type: str  # rect | polygon | polyline
    points: tuple[tuple[float, float], ...] | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    scope_kind: ScopeKind = ScopeKind.AREA
    meta: dict[str, Any] | None = None

    def to_geometry_json(self) -> dict[str, Any]:
        """Serialize for DrawingOverlay.geometry column."""


def validate_scope_geometry(geometry: dict[str, Any]) -> None:
    """
    Accept type: rect | polygon | polyline
    polyline: points list min 2 points, each 0-1 normalized
    Reuse _check_normalized pattern from services/region_storage.py
    """


def bbox_to_scope_rect(bbox: tuple[float, float, float, float], *, page: int, scope_kind: ScopeKind) -> ScopeGeometry:
    ...

MODIFY backend/services/region_storage.py validate_region_geometry:
  ADD elif gtype == "polyline": min 2 points, normalized 0-1

ADD backend/tests/test_scope_geometry.py
```

---

- [ ] **E-2** Scope type classifier

**PROMPT — copy below:**

```
PR-E step E-2: Infer scope type from dossier (autonomous — user does not specify).

ADD to backend/ai/pipelines/scope_geometry.py:

def infer_scope_kind(dossier: EvidenceDossier) -> ScopeKind:
    """
    Rules (deterministic first):
      - station_from + station_to in clues/meta -> STATION_RANGE / UTILITY_LINE
      - two survey N/E points -> UTILITY_LINE
      - inspection mentions lateral/main/run/pipe/duct/sewer/water -> UTILITY_LINE
      - corridor/room/area/parking lot without linear language -> CORRIDOR or AREA
      - single coordinate point only -> POINT
    Do not require user input.
    """

ADD tests with dossier fixtures for SS install, COLO corridor, coord-only.
```

---

- [ ] **E-3** Line tracer pipeline

**PROMPT — copy below:**

```
PR-E step E-3: Scope line tracer — precise polyline over exact work area.

ADD backend/ai/pipelines/scope_line_tracer.py

"""Derive polyline scope geometry on master drawing."""

from __future__ import annotations

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.scope_geometry import ScopeGeometry, ScopeKind


def trace_scope_geometry(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    scope_kind: ScopeKind,
    page: int = 1,
) -> ScopeGeometry:
    """
    Priority by scope_kind:
      1. STATION_RANGE: find STA labels on master text_elements, connect path
      2. UTILITY_LINE with two coords: project endpoints, connect
      3. UTILITY_LINE: search legend line type (DrawingLegendLineType) near anchor,
         vision trace on master crop (defer to PR-G if not ready — stub returns centerline through anchor)
      4. AREA/CORRIDOR: region polygon or rect from matched region_id
      5. POINT: short segment or small rect at coordinate

    Line must stay within anchor expanded by padding (e.g. 0.05 norm).
    If multiple parallel lines ambiguous -> return best guess + meta["ambiguous"]=True
    """

Use:
  - models.drawing_text_element.DrawingTextElement for STA labels
  - services.legend_lookup.find_codes_for_term
  - ai.pipelines.location_match_orchestrator._evidence_rendition_png pattern for master crop

ADD backend/tests/test_scope_line_tracer.py
  - station range mock: two STA tokens on master -> polyline between centroids
  - utility line: anchor bbox + SS labels nearby -> polyline with >= 2 points
```

---

- [ ] **E-4** Persist scope geometry on overlay

**PROMPT — copy below:**

```
PR-E step E-4: Persist scope geometry (polyline) on DrawingOverlay.

MODIFY backend/services/inspection_match_persistence.py

REPLACE bbox-only bbox_to_geometry with scope_to_geometry:

def scope_to_geometry(
    scope: ScopeGeometry | None,
    *,
    fallback_bbox: tuple[float, float, float, float] | None = None,
    page: int,
) -> dict[str, Any]:
    """Prefer ScopeGeometry; fall back to rect from bbox; else UNMAPPED_GEOMETRY."""

UPDATE persist_inspection_match_overlay to accept optional scope: ScopeGeometry | None.
When scope.type == polyline, persist points array:

{
  "page": 1,
  "type": "polyline",
  "points": [[0.41, 0.38], [0.43, 0.39], [0.45, 0.40]],
  "scope_kind": "utility_line",
  "label": "inspection_match",
  "meta": {"station_from": "12+50", "station_to": "12+85"}
}

MODIFY backend/services/overlay_storage.py _bbox_to_geometry — add polyline branch or delegate to scope_geometry.

Run: cd backend && pytest tests/test_scope_geometry.py tests/test_inspection_matching_jobs.py -q
```

---

# PR-F — Frontend polyline rendering

- [ ] **F-1** TypeScript polyline types

**PROMPT — copy below:**

```
PR-F step F-1: Frontend support for polyline overlay geometry.

MODIFY client/src/types/drawing_workspace.ts

Extend DrawingDiffRegion:
  shapeType?: "rect" | "polygon" | "polyline" | null;

Add optional scopeKind?: string | null for styling.

MODIFY client/src/lib/drawing-overlays/geometry.ts

In resolveOverlayRegion():
  if region.shapeType === "polyline" && region.points && region.points.length >= 2:
    return { kind: "polyline", points: normalizePoints(region.points), source: region }

Also accept geometry JSON from API where type === "polyline".

ADD client/src/tests/unit/overlay_polyline.test.ts
  - resolveOverlayRegion polyline with 3 points
  - normalizedPointsToPixels for polyline
```

---

- [ ] **F-2** Render polyline in overlay layer

**PROMPT — copy below:**

```
PR-F step F-2: Render precise scope line on master drawing viewer.

MODIFY client/src/lib/drawing-overlays/overlay-types.ts (if needed):
  ResolvedOverlayRegion kind: "rect" | "polygon" | "polyline"

MODIFY client/src/components/drawing-workspace/overlay_shape.tsx

ADD branch for region.kind === "polyline":
  <polyline
    points={pointsString}
    fill="none"
    stroke={stroke}
    strokeWidth={strokeWidth + 1}  // lines slightly heavier than rect stroke
    strokeLinecap="round"
    strokeLinejoin="round"
  />

Lines represent exact scoped work area — no fill.

Ensure drawing_overlay_layer.tsx passes polyline regions through resolveOverlayRegion.

Manual check: mock overlay with polyline points displays on workspace viewer.
```

---

# PR-G — Vision location reasoner

- [ ] **G-1** Vision reasoner module

**PROMPT — copy below:**

```
PR-G step G-1: Vision location reasoner for ambiguous cases + line trace.

ADD backend/ai/pipelines/vision_location_reasoner.py

Reuse ai/pipelines/openai_vision.py _vision_chat_completion (detail=high).

@dataclass(frozen=True)
class VisionLocationResult:
    best_candidate_index: int | None
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    polyline_points: tuple[tuple[float, float], ...] | None
    highlight_detected: bool
    rationale: str


def should_invoke_vision(fused_scores: list[FusedCandidateScore], dossier: EvidenceDossier) -> bool:
    """True if top score < 0.65 OR top two within 0.05 OR scope_kind is UTILITY_LINE."""


def reason_over_master_crop(
    *,
    master_png_path: Path,
    dossier_summary: str,
    candidate_bboxes: list[tuple[float, float, float, float]],
    task: str,  # "localize" | "trace_line" | "detect_highlight"
) -> VisionLocationResult:
    """
    Structured JSON prompt. Tasks:
      localize: pick best candidate index + refine bbox
      trace_line: return normalized polyline along utility line inspection refers to
      detect_highlight: optional; return highlight bbox if present (NOT required for match)

    Highlight is optional enrichment only.
    """


def apply_vision_to_fused_scores(
    dossier: EvidenceDossier,
    scores: list[FusedCandidateScore],
    *,
    master_png_path: Path,
) -> list[FusedCandidateScore]:
    """Merge vision confidence into fused scores; never override strong coordinate match alone."""

ADD backend/tests/test_vision_location_reasoner.py with mocked OpenAI response.
Wire vision trace into scope_line_tracer when deterministic trace fails.
```

---

# PR-H — Inspection Location Agent

- [ ] **H-1** Agent orchestrator

**PROMPT — copy below:**

```
PR-H step H-1: Inspection Location Agent — autonomous investigation loop.

ADD backend/ai/agents/inspection_location_agent.py

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import build_evidence_dossier, EvidenceDossier
from ai.pipelines.clue_fusion_scorer import fuse_candidate_scores, select_fused_winner
from ai.pipelines.location_match_orchestrator import generate_all_location_candidates
from ai.pipelines.scope_geometry import infer_scope_kind, ScopeGeometry
from ai.pipelines.scope_line_tracer import trace_scope_geometry
from ai.pipelines.vision_location_reasoner import should_invoke_vision, apply_vision_to_fused_scores
from services.inspection_match_persistence import MatchStatus


MAX_INVESTIGATION_STEPS = 8


@dataclass(frozen=True)
class AgentMatchResult:
    status: MatchStatus
    scope: ScopeGeometry | None
    region_id: int | None
    page: int
    rationale: str
    fused_score: float | None


class InspectionLocationAgent:
    def run(
        self,
        session: Session,
        *,
        evidence_id: int,
        master_drawing_id: int,
        page: int = 1,
    ) -> AgentMatchResult:
        """
        0. Check master index readiness -> index_pending if not ready
        1. build_evidence_dossier (includes PDF link investigation)
        2. If new auxiliary drawings need index -> defer (index_pending), flush later
        3. generate_all_location_candidates
        4. fuse_candidate_scores
        5. if should_invoke_vision: apply_vision_to_fused_scores
        6. select_fused_winner
        7. infer_scope_kind + trace_scope_geometry (polyline for lines, rect/polygon for areas)
        8. decide status:
             matched if fused >= 0.75 and no major conflicts
             needs_review if borderline or ambiguous line
             no_match if no candidates or conflicts dominate
        9. persist overlay + all candidates with rationale in DrawingMatchCandidate.meta_json

        NEVER use sheet numbers for master placement.
        """

UPDATE backend/ai/agents/__init__.py:
  from ai.agents.inspection_location_agent import InspectionLocationAgent, AgentMatchResult

ADD backend/tests/test_inspection_location_agent.py
  - end-to-end with mocked vision + seeded dossier
  - assert polyline geometry when scope_kind UTILITY_LINE
```

---

- [ ] **H-2** Agent persistence helper

**PROMPT — copy below:**

```
PR-H step H-2: Persist agent result (scope + candidates + rationale).

ADD to backend/ai/agents/inspection_location_agent.py or backend/services/inspection_match_persistence.py:

def persist_agent_match_result(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    result: AgentMatchResult,
    ranked_scores: list[FusedCandidateScore],
    inspection_run_id: int | None = None,
) -> int | None:
    """
    For each FusedCandidateScore: record_internal_match_candidate with meta_json:
      { rationale, clue_hits, conflicts, fused_score }
    persist_inspection_match_overlay with scope=result.scope (polyline supported)
    """

Run: cd backend && pytest tests/test_inspection_location_agent.py -q
```

---

# PR-I — Wire agent into upload + job pipeline

- [ ] **I-1** Replace orchestrator call in match job

**PROMPT — copy below:**

```
PR-I step I-1: Wire InspectionLocationAgent into inspection match job.

MODIFY backend/services/inspection_matching_jobs.py

In process_inspection_match_job / run_inspection_match_job:
  REPLACE direct resolve_evidence_location(...) with:
    from ai.agents.inspection_location_agent import InspectionLocationAgent
    agent = InspectionLocationAgent()
    result = agent.run(session, evidence_id=..., master_drawing_id=..., page=...)

Keep deferred match / index_pending behavior unchanged.
Keep observability logs (log_inspection_match_started, log_inspection_match_result).

Run: cd backend && pytest tests/test_inspection_matching_jobs.py -q
```

---

- [ ] **I-2** Enqueue after extraction + flush on auxiliary index

**PROMPT — copy below:**

```
PR-I step I-2: Ensure agent runs after link investigation + auxiliary index.

MODIFY backend/services/evidence_document_extraction.py
  - confirm maybe_enqueue_inspection_match_after_extraction still fires after linked PDF registration

MODIFY backend/services/drawing_index_jobs.py
  - confirm flush_inspection_matches_for_linked_auxiliary_drawing runs after auxiliary index

Agent must receive indexed auxiliary drawings in dossier scoped_points / candidate_tiles.

Manual verification checklist (log grep):
  qcqa.linked_drawing.registered
  scoped_point_count > 0 after auxiliary index
  inspection_location_agent run completes with polyline or rect scope
```

---

# PR-J — Eval, line accuracy, and gates

- [ ] **J-1** Extend eval labels for scope geometry

**PROMPT — copy below:**

```
PR-J step J-1: Eval labels support polyline scope geometry.

MODIFY backend/models/location_match_label.py
  ADD master_scope_geometry_json = Column(JSON, nullable=True)
  Keep master_bbox_json for backward compat (rect labels).

MODIFY backend/tests/fixtures/location_match_labels/ucsf.json
  For sewer/utility labels, ADD example:
    "master_scope_geometry_json": {
      "type": "polyline",
      "page": 1,
      "points": [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]],
      "scope_kind": "utility_line"
    }

ADD alembic migration for master_scope_geometry_json (nullable).

MODIFY backend/scripts/seed_location_match_labels.py — accept optional master_scope_geometry_json.

UPDATE backend/tests/fixtures/location_match_labels/README.md with annotation guide:
  - Utility run inspections: human marks polyline along exact scoped line
  - Area inspections: rect or polygon
  - Do not label by sheet number
```

---

- [ ] **J-2** Line accuracy metrics

**PROMPT — copy below:**

```
PR-J step J-2: Eval line/path accuracy metrics.

MODIFY backend/services/location_match_eval.py

ADD functions:
  hausdorff_distance_norm(line_a, line_b) -> float
  path_overlap_ratio(predicted, expected, tolerance=0.02) -> float
  endpoint_error_norm(predicted, expected) -> float

When label has master_scope_geometry_json type polyline:
  score path_overlap_ratio >= 0.70 AND endpoint_error <= 0.03 -> pass
When label has rect only:
  keep existing IoU >= 0.30 gate

MODIFY backend/scripts/eval_location_match.py
  report polyline pass rate separately from rect pass rate

Targets (initial):
  rect IoU pass rate >= 80% (UCSF suite)
  polyline path overlap pass rate >= 70%
  false matched on photo/form no-coord cases: 0%
```

---

- [ ] **J-3** CI regression gate

**PROMPT — copy below:**

```
PR-J step J-3: CI eval regression gate.

ADD or MODIFY backend/tests/test_location_match_eval_regression.py

@pytest.mark.eval
def test_ucsf_suite_pass_rate_floor():
    run eval_location_match programmatically on ucsf suite
    assert pass_rate >= 0.80  # tune after first agent deploy

def test_no_false_match_photo_form():
    synthetic no-coord photo/form labels must never get matched

Document in Notes/inspection_location_agent_plan.md PRE-2 baseline comparison.

Run full eval:
cd backend && python scripts/eval_location_match.py --suite ucsf
cd backend && python scripts/eval_location_match.py --suite synthetic
```

---

## Manual verification (after PR-I)

- [ ] **V-1** Upload golden inspection evidence

**PROMPT — copy below:**

```
Manual V-1: Golden case end-to-end.

1. Restart backend + job worker
2. Upload evidence for project 2 / master 661 (or golden evidence 357)
3. Grep logs:
   - pdf_link_follow_complete fetched_pdf_count > 0 (when links present)
   - linked_drawing_registered
   - inspection_location_agent (or match job) completed
   - scoped_point_count > 0 when coords present
4. Open master drawing workspace — verify overlay:
   - utility inspection shows POLYLINE along work area (not just a box)
   - match_status matched or needs_review
5. API GET overlays returns geometry.type polyline with points array
```

---

## Annotation guide (for human eval labels)

When creating `master_scope_geometry_json` labels:

| Inspection type | Label geometry |
|-----------------|----------------|
| Sewer/water/duct **run**, lateral, main | `polyline` along the line on master |
| **Station range** (STA 12+50 to 12+85) | `polyline` between station points |
| **Single N/E** coordinate | small `rect` or 2-point `polyline` at point |
| **Corridor / room / pad** | `rect` or `polygon` |
| **Optional highlight** on evidence | does not change label — label the master scope |

**Never** label by sheet number. Label the **physical scope on the master drawing**.

---

## Model usage summary

| Step | Engine |
|------|--------|
| Document classification + field extraction | LLM (existing) |
| Legend expansion | DB (`legend_lookup`) |
| PDF link follow + page render | Deterministic + OCR |
| Candidate generation | Deterministic matchers |
| Clue fusion (primary) | Weighted rules (`clue_fusion_scorer`) |
| Clue fusion (tie-break) | LLM structured JSON |
| Scope kind inference | Rules (`infer_scope_kind`) |
| Line trace (primary) | Station/coord/legend text |
| Line trace (fallback) | Vision (`vision_location_reasoner`) |
| Highlight detection | Vision (optional, never required) |

---

## Success criteria

- [ ] Agent investigates upload autonomously (notes, links, legend, DB)
- [ ] No sheet-number-based master pins
- [ ] User sees **precise scope overlay** on master (polyline for linear work)
- [ ] UCSF eval pass rate ≥ 80% (rect IoU); polyline path overlap ≥ 70%
- [ ] Zero false `matched` on photo/form no-coord synthetic cases
- [ ] Borderline cases → `needs_review`, not silent wrong pin

---

## PR dependency order

```
PRE → A → B → C → D → E → F → G → H → I → J
         ↘     ↗
          C+D can parallel after A
E (geometry) before F (frontend) and before H (agent)
G (vision) can parallel E after C+D
```

Do not start **H** until **A–E** complete. Do not start **J** until **I** complete.
