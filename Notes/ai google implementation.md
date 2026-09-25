# Google Document AI — Master Drawing OCR Implementation

**Goal:** Replace **ad-hoc vision OCR** (Tesseract + OpenAI vision on rasterized pages) for **master drawing text index** with **Google Document AI** (`OCR_PROCESSOR`), while keeping **native PDF text** and extending the existing **hybrid merge** to three sources.

**Why:** Masters are large, rotation-heavy CAD PDFs. Tesseract is single-pass horizontal @ 200 DPI; OpenAI vision was a poor fit for structured token+bbox ingest. Document AI returns **tokens + normalized bboxes + confidence** in one pass — closer to what `DrawingTextElement` already stores.

**Golden validation:** drawing **1691** / project **688** (and legacy **661** if still on disk). Keyword checklist: SSMH, MLK, HIGHWAY, legend PROPERTY/LINE, notes block.

**Out of scope (do not delete):**
- **`vision_location_reasoner`** — scope **polyline** fallback, not text OCR.
- **Native PDF** extract (`document_text_extraction._pdf_text_layer`) — keep always.
- **PyMuPDF render** for renditions / sheet digitization — unchanged.
- **Inspection / evidence photos** — may keep Tesseract or a separate path until a second phase.

**Related:**
- `Notes/pdf poly line.md` — vector lines (orthogonal to OCR)
- `backend/ai/pipelines/master_drawing_indexer.py` — index orchestrator
- `backend/ai/pipelines/hybrid_text_merge.py` — merge today: native + OCR
- `backend/scripts/audit_drawing_index_coverage.py` — validation export

**How to use:** Work **Phase 0 → 7**. Check `[ ]` when done. Each phase lists **Add**, **Modify**, **Delete (later)**, and **TEST**.

---

## Current vs target

```
TODAY (master index text)
─────────────────────────
  native PDF words (PyMuPDF)
  + OCR via ocr_engine (Tesseract and/or OpenAI vision on pixmap)
  → merge_native_and_ocr_words (2-way)
  → DrawingTextElement.source: native_pdf | tesseract | openai_vision | hybrid_pdf


TARGET
──────
  native PDF words (unchanged)
  + Document AI batch OCR (GCS in/out, one processor per env)
  + (optional, Phase 5 only) Tesseract in parallel for A/B
  → merge_native_ocr_and_document_ai_words (3-way)
  → DrawingTextElement.source: native_pdf | document_ai | tesseract | hybrid_pdf
  → Deprecate openai_vision for master OCR after sign-off
```

---

## Phase 0 — GCP project & credentials

**App code (done):** `backend/config.py` + `backend/.env.example` expose the env vars below. Defaults keep Document AI **off** until you set `DOCUMENT_AI_ENABLED=true` and fill required fields.

**Ops (you run once per environment):**

1. **Project + billing** — pick or create a project; link a billing account.
2. **Enable APIs**

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us   # Document AI batch location: us or eu (not arbitrary GCP regions)

gcloud config set project "$PROJECT_ID"
gcloud services enable documentai.googleapis.com storage.googleapis.com
```

3. **GCS buckets** (same `LOCATION` as Document AI, e.g. `US` multi-region or `us-central1`)

```bash
export INPUT_BUCKET="${PROJECT_ID}-document-ai-input"
export OUTPUT_BUCKET="${PROJECT_ID}-document-ai-output"

gcloud storage buckets create "gs://${INPUT_BUCKET}" --location=US --uniform-bucket-level-access
gcloud storage buckets create "gs://${OUTPUT_BUCKET}" --location=US --uniform-bucket-level-access
```

4. **Service account + IAM**

```bash
export SA_NAME=document-ai-master-index
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME" --display-name="Master drawing Document AI batch"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/documentai.apiUser"

gcloud storage buckets add-iam-policy-binding "gs://${INPUT_BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"

gcloud storage buckets add-iam-policy-binding "gs://${OUTPUT_BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"
```

- **Render / other non-GCP workers:** download a JSON key only into a secret store; set `GOOGLE_APPLICATION_CREDENTIALS` to that path on the worker (never commit the file).
- **GCP-hosted workers:** prefer **Workload Identity** — bind the same SA to the runtime; omit long-lived keys.

5. **Budget alert** — Billing → Budgets → e.g. $50/mo with email at 50%/90% (~$0.01/page OCR).

6. **Local dev** — after Phase 1 processor id exists, add to `backend/.env` (see `.env.example` block).

| Env var | Purpose |
|---------|---------|
| `GOOGLE_CLOUD_PROJECT` | Project id (`$PROJECT_ID`) |
| `DOCUMENT_AI_LOCATION` | `us` or `eu` (must match processor + API endpoint) |
| `DOCUMENT_AI_PROCESSOR_ID` | Full resource name from Phase 1 (`projects/.../processors/...`) |
| `DOCUMENT_AI_GCS_INPUT_BUCKET` | `$INPUT_BUCKET` (name only, no `gs://`) |
| `DOCUMENT_AI_GCS_OUTPUT_BUCKET` | `$OUTPUT_BUCKET` |
| `DOCUMENT_AI_ENABLED` | `true` only after Phase 4 wiring — safe to set vars early while false |
| `DOCUMENT_AI_PARALLEL_TESSERACT` | Phase 5 A/B — run Tesseract alongside Doc AI |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to SA JSON (local/dev or non-WIF deploy) |

**TEST**

```bash
gcloud services list --enabled --filter='name:documentai.googleapis.com'
cd backend && PYTHONPATH=. ./venv/bin/python -c "from config import settings, document_ai_configured; print('enabled', settings.document_ai_enabled, 'configured', document_ai_configured())"
```

Expect `configured False` until processor id + buckets + project are set.

---

## Phase 1 — One-time processor create

**Add:** `backend/scripts/create_document_ai_processor.py` (run once per env)

```bash
cd backend
./venv/bin/pip install google-cloud-documentai   # or pip install -r requirements.txt
# ADC: gcloud auth application-default login  OR  GOOGLE_APPLICATION_CREDENTIALS=...

./venv/bin/python scripts/create_document_ai_processor.py
# → prints DOCUMENT_AI_PROCESSOR_ID=projects/.../locations/us/processors/...

./venv/bin/python scripts/create_document_ai_processor.py --list   # avoid duplicate creates
```

Uses `GOOGLE_CLOUD_PROJECT` and `DOCUMENT_AI_LOCATION` from `.env` when flags omitted. Processor type is **`OCR_PROCESSOR`** (general OCR — no CAD-specific processor).

**Delete:** Nothing.

**TEST:** Processor visible in Cloud Console; `DOCUMENT_AI_PROCESSOR_ID` in `.env`; `document_ai_configured()` true once buckets are set too.

---

## Phase 2 — Batch pipeline module (no sync API)

**Why batch only:** Sync `process_document` ≈ **15 pages / ~20MB** cap. Masters and backfills need **`batch_process_documents`** (GCS → GCS, LRO poll or Pub/Sub).

**Add:**

| File | Role |
|------|------|
| `backend/ai/pipelines/document_ai_batch.py` | Upload PDF to GCS, start batch job, poll operation, list output JSON paths |
| `backend/ai/pipelines/document_ai_parser.py` | `Document` JSON → `list[PositionedWord]` (`token_source="document_ai"`) |
| `backend/services/document_ai_storage.py` | Thin GCS upload/download helpers (or reuse existing storage patterns) |
| `backend/tests/test_document_ai_parser.py` | Fixture JSON → words (no live GCP in CI) |
| `backend/tests/fixtures/document_ai/sample_page.json` | Minimal exported page |

**Parser mapping (slot into existing schema):**

```python
def document_ai_tokens_to_words(document, *, page_index: int) -> list[PositionedWord]:
    page = document.pages[page_index]
    for token in page.tokens:
        text = _text_from_anchor(token.layout.text_anchor, document.text)
        # normalized_vertices → BoundingBox in page pixel space
        bbox = _bbox_from_normalized_poly(token.layout.bounding_poly, page.dimension)
        confidence = float(token.layout.confidence or 0.0)
        # PositionedWord(..., ocr_confidence=confidence, token_source="document_ai")
```

**Validate:** Doc AI bboxes are **0–1 normalized** — map into `BoundingBox` with `page_width`/`page_height` from page dimension; **confirm on rotated 1691** that gutters (Highway 24) land without extra rotation hacks.

**Modify:**
- `backend/config.py` — fields from Phase 0 table ✅
- `backend/.env.example` — document AI block ✅

**Delete:** Nothing yet.

**TEST:** `./venv/bin/python -m pytest tests/test_document_ai_parser.py -q`; optional live `scripts/run_document_ai_batch.py --pdf /path/to/master.pdf`.

---

## Phase 3 — Three-way hybrid merge

**Add:** `backend/ai/pipelines/hybrid_text_merge.py` (extend, do not fork)

```python
OCR_SOURCE_DOCUMENT_AI = "document_ai"

def merge_native_ocr_and_document_ai_words(
    native_words: list[PositionedWord],
    document_ai_words: list[PositionedWord],
    tesseract_words: list[PositionedWord] | None = None,
    *,
    prefer_order: tuple[str, ...] = ("native_pdf", "document_ai", "tesseract"),
) -> list[PositionedWord]:
    """Dedupe by page + fractional center + text similarity.

    On duplicate, keep the source listed earlier in prefer_order.
    """
```

**Modify:**
- Keep `merge_native_and_ocr_words` as thin wrapper calling 3-way with `tesseract_words=ocr_words` for backward compat during migration.

**Delete (Phase 7 only):** Tesseract branch inside merge when A/B complete.

**TEST:** `./venv/bin/python -m pytest tests/test_hybrid_text_merge.py -q` ✅

---

## Phase 4 — Wire `master_drawing_indexer.py`

**Modify:** `extract_drawing_document()` / new branch:

```text
1. native = extract_document(file_path)     # unchanged
2. if settings.document_ai_enabled:
       docai = extract_document_via_document_ai(file_path)  # batch or cached output
   else:
       docai = ExtractedDocument(empty)  # or skip
3. if settings.document_ai_parallel_tesseract:   # Phase 5 A/B only
       tess = extract_document_via_ocr(file_path)
   else:
       tess = empty
4. merged = merge_native_ocr_and_document_ai_words(native.words, docai.words, tess.words)
5. source_format = HYBRID_PDF
```

**Add:**
- `extract_document_via_document_ai()` in `document_text_extraction.py` OR `document_ai_batch.py` returning `ExtractedDocument` with `SourceFormat.SCANNED_PDF` or new `SourceFormat.DOCUMENT_AI_PDF` (optional enum value).
- `element_source()` / persist path: map token → `document_ai` in `DrawingTextElement.source`.
- **Index job:** `drawing_index_jobs.py` — if batch async, enqueue **poll job** or store `document_ai_operation_id` on drawing `index_stats_json` until complete (avoid blocking worker 30+ min).

**Modify:**
- `models/drawing_text_element.py` comment: `native_pdf | document_ai | tesseract | openai_vision | hybrid_pdf`
- `master_drawing_indexer._ocr_token_source()` — return `document_ai` when enabled.

**Delete (Phase 7):** Default path that calls `extract_document_via_ocr` for masters when Doc AI enabled.

**Do not wire Doc AI into:** evidence photo ingest, arbitrary `ocr_engine.ocr_image` callers, unless explicitly scoped later.

**TEST:** Unit tests in `test_master_drawing_indexer.py` (Doc AI path mocked). Live: re-index 1691 with `DOCUMENT_AI_ENABLED=true`; `audit_drawing_index_coverage.py --drawing-id 1691`.

---

## Phase 5 — Validation & A/B (before decommission)

**Run:**

```bash
cd backend && PYTHONPATH=. ./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 1691 --project-id 688 --export tokens_1691_docai.tsv
```

**Compare tables:**

| Metric | Baseline (notes) | Target |
|--------|------------------|--------|
| Native tokens | ~281 | unchanged |
| Tesseract tokens | ~1184 | optional parallel |
| Doc AI tokens | 0 | TBD |
| HIGHWAY in gutter bbox | missing | present |
| Legend LINE fragments | 7× LINE | cluster rows (separate legend work) |

**Decision gate:**
- If Doc AI ≥ Tesseract on checklist **without** multi-orientation Tesseract → **skip** planned multi-orientation OCR for masters.
- If not → keep Tesseract as secondary source in 3-way merge until tuned.

**Add:** `scripts/compare_index_sources.py` ✅ — DB and/or TSV diff + keyword checklist.

```bash
# After re-index with Document AI — source mix + checklist
cd backend && PYTHONPATH=. ./venv/bin/python scripts/compare_index_sources.py \\
  --drawing-id 1691 --project-id 688 --gutter-x-max 0.15

# A/B: export baseline before re-index, then diff
./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 1691 --project-id 688 \\
  --export tokens_1691_baseline.tsv
# ... re-index ...
./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 1691 --project-id 688 \\
  --export tokens_1691_docai.tsv
./venv/bin/python scripts/compare_index_sources.py \\
  --baseline tokens_1691_baseline.tsv --current tokens_1691_docai.tsv

# Quick checklist on audit alone
./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 1691 --project-id 688 --checklist
```

**TEST:** `./venv/bin/python -m pytest tests/test_drawing_index_validation.py -q`

**Delete:** Nothing until gate passes.

---

## Phase 6 — Index worker / backfill

**Add:** ✅
- Backfill: `scripts/backfill_document_ai_index.py --project-id 688 --drawing-ids 1691` (or `--all-masters`, `--dry-run`)
- Cache: `services/document_ai_cache.py` — `batch-output/by-drawing/{drawing_id}/{sha256}/` (reuse JSON, skip batch when shards exist)
- While batch LRO runs: `index_status=pending_document_ai` + `index_stats_json.document_ai_pending`

**Modify:** ✅ `drawing_index_jobs.py` (`set_document_ai_pending`, clear on success); `document_ai_batch.py` + indexer pass `drawing_id`.

**TEST:** `./venv/bin/python -m pytest tests/test_document_ai_cache.py -q`; live backfill after GCP + `DOCUMENT_AI_ENABLED=true`.

**Note:** Index job still **blocks** on batch LRO in-process; cache avoids **re-billing** on re-index. Split poll worker is future work if timeouts bite.

---

## Phase 7 — Remove / deprecate (after sign-off)

**Deprecate then delete (masters only first):**

| Item | Action |
|------|--------|
| `OCR_BACKEND=openai_vision` for master index | Remove from docs; reject in config when `DOCUMENT_AI_ENABLED=true` |
| `ocr_engine.ocr_image_openai_vision` | Stop calling from `extract_document_via_ocr` for PDF masters |
| `ai/pipelines/openai_vision.py` | **Keep file** if inspection/GPT still imports it; remove OCR-only helpers if unused |
| Tesseract master path | Make opt-in (`DOCUMENT_AI_PARALLEL_TESSERACT=false` default off) |
| Multi-orientation Tesseract plan (if not built) | **Cancel** for masters if Doc AI validates rotation |
| Health `/health` emphasis on `tesseract_available` | Add `document_ai_configured` |

**Do not delete:**
- `ocr_engine.py` entirely — photos, aux sheets, dev fallback.
- `openai_chat_model` / inspection GPT — unrelated to Doc AI OCR.
- Native PDF extraction or `pdf_display_space` rotation fixes — still needed for native layer.

---

## File map summary

| Action | Path |
|--------|------|
| **Add** | `document_ai_batch.py`, `document_ai_parser.py`, `document_ai_storage.py` (or GCS in batch module) |
| **Add** | `scripts/create_document_ai_processor.py`, `scripts/run_document_ai_batch.py`, `scripts/backfill_document_ai_index.py` |
| **Add** | `tests/test_document_ai_parser.py`, `tests/fixtures/document_ai/` |
| **Modify** | `hybrid_text_merge.py`, `master_drawing_indexer.py`, `document_text_extraction.py`, `drawing_index_jobs.py`, `config.py`, `.env.example` |
| **Modify** | `drawing_text_element.py` (comment + any index on source) |
| **Delete later** | OpenAI-vision-as-OCR wiring for masters; optional Tesseract default for masters |

---

## Dependencies

**Add to** `backend/requirements.txt` (versions pinned in PR):

```text
google-cloud-documentai
google-cloud-storage
```

---

## Cost / ops

- **OCR_PROCESSOR:** ~ **$0.01/page**, one-time ingest per master revision → negligible at current volume.
- Enable **GCP budget alerts**; log `document_ai_pages_processed` in `index_stats_json`.

---

## PROMPT — Phase 2 + 3 (Agent)

```text
Implement Google Document AI batch OCR for master drawings:

1. Add document_ai_parser.py: fixture-driven tests, map tokens to PositionedWord with token_source=document_ai.
2. Add document_ai_batch.py skeleton: GCS upload, batch_process_documents, poll LRO, download JSON (integration script gated by env).
3. Extend hybrid_text_merge.py with merge_native_ocr_and_document_ai_words (3-way, prefer native > document_ai > tesseract).
4. Add config fields DOCUMENT_AI_* to config.py and .env.example.
Do NOT remove Tesseract or openai_vision yet. Do NOT wire master_drawing_indexer until tests pass.
```

---

## PROMPT — Phase 4 (Agent)

```text
Wire document AI into master_drawing_indexer.extract_drawing_document:
- When DOCUMENT_AI_ENABLED, call extract_document_via_document_ai instead of extract_document_via_ocr for the OCR leg.
- Persist DrawingTextElement.source=document_ai from token_source.
- Extend index_stats_json with document_ai_pages, batch_operation_id, parse timing.
- Update test_master_drawing_indexer.py with mocked document AI words.
Keep native extract unconditional. Keep merge 3-way with tesseract optional via flag.
```

---

## Summary

- **Add:** GCP batch OCR path, parser to `PositionedWord`, 3-way merge, indexer + job wiring, validation scripts.
- **Keep:** Native PDF, rendition pipeline, vision scope tracer, inspection GPT.
- **Remove (later):** OpenAI vision as master OCR; default Tesseract on masters after Doc AI proves coverage on **1691** / checklist.
