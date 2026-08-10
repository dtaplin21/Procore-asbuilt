# Universal Location-Match Eval Labels — Manual Entry Checklist

**Goal:** Eval labels work for any project. UCSF is suite data only — not product truth.

**How to use:** Work top → bottom. Copy one **PROMPT** into Cursor Agent. Check `[x]` when done.

**Do not:** Hard-code project_id, evidence_id, drawing_id, N/E, or sheet refs in matcher/orchestrator.

---

## File map (touch these)

| Action | Path |
|--------|------|
| ADD | `backend/tests/fixtures/location_match_labels/ucsf.json` |
| ADD | `backend/tests/fixtures/location_match_labels/synthetic.json` |
| ADD | `backend/tests/fixtures/location_match_labels/README.md` |
| ADD | `backend/scripts/export_location_match_label.py` |
| ADD | `backend/tests/test_no_hardcoded_ucsf_match_ids.py` |
| ADD | `backend/services/location_match_label_io.py` (if shared loaders extracted) |
| MOVE/DELETE | `backend/tests/fixtures/location_match_labels.json` → `ucsf.json`, then delete root file |
| MODIFY | `backend/models/location_match_label.py` |
| MODIFY | `backend/alembic/versions/` (new migration) |
| MODIFY | `backend/scripts/seed_location_match_labels.py` |
| MODIFY | `backend/scripts/eval_location_match.py` |
| MODIFY | `backend/services/location_match_eval.py` |
| MODIFY | `backend/scripts/verify_golden_location_match.py` → rename + generalize |
| MODIFY | `backend/tests/test_location_match_labels_seed.py` |
| MODIFY | `backend/tests/test_location_match_eval.py` |
| MODIFY | `Notes/inspection_upload_pipeline.md` (PR-G wording only) |

---

# U-0 — Schema: add `suite`

- [x] **U-0.1** Add `suite` column to model + migration

**PROMPT — copy below:**

```
U-0.1: Add suite to location_match_labels.

FILES:
- MODIFY backend/models/location_match_label.py
  After label_id column, add:
    suite = Column(String, nullable=False, server_default="default", index=True)
- ADD alembic migration (follow g1l2m3a4b5e6_add_location_match_labels.py pattern):
  - upgrade: add column suite String NOT NULL server_default 'default', index ix_location_match_labels_suite
  - backfill existing rows suite='ucsf' if any
  - downgrade: drop index + column
- MODIFY backend/scripts/seed_location_match_labels.py
  - Add "suite" to REQUIRED_FIELDS
  - validate_entry: suite must be non-empty str
  - upsert: set row.suite from entry["suite"]
- MODIFY backend/services/location_match_eval.py
  - EvalLabel: add suite: str
  - eval_label_from_json / eval_label_from_row: map suite
```

---

# U-1 — Multi-suite fixture layout

- [x] **U-1.1** Split fixtures into suite files

**PROMPT — copy below:**

```
U-1.1: Restructure location match label fixtures.

1. CREATE directory backend/tests/fixtures/location_match_labels/

2. MOVE content from backend/tests/fixtures/location_match_labels.json
   → backend/tests/fixtures/location_match_labels/ucsf.json
   Add "suite": "ucsf" to EVERY object in the array.
   Keep all existing fields/values (ucsf-* label_ids stay).

3. CREATE backend/tests/fixtures/location_match_labels/synthetic.json
   with exactly 2 labels (suite="synthetic"), fixture-only (evidence_id null):
   - synthetic-coord-matched: expected_method coordinate_lookup, matched,
     has_coordinate_signal true, tiny master_bbox_json rect on page 1
     (use placeholder x/y/w/h > 0; project_id=1; master_drawing_id=1 —
     these IDs are for schema only; eval will skip missing evidence)
   - synthetic-no-match: expected_method unresolved, no_match,
     has_coordinate_signal false, zero-area bbox, evidence_kind photo

4. CREATE backend/tests/fixtures/location_match_labels/README.md:
   # Location match eval suites
   - One JSON array file per suite
   - Required fields: suite, label_id, project_id, master_drawing_id,
     master_bbox_json, expected_method, expected_match_status,
     has_coordinate_signal, has_station_signal, has_reference_signal, evidence_kind
   - Optional: evidence_id, inspection_run_id, evidence_fixture_path, rotation_deg, notes
   - Add a new project by adding <slug>.json — do not hard-code IDs in matchers

5. DELETE backend/tests/fixtures/location_match_labels.json
```

---

- [x] **U-1.2** Seed script loads suite dir / filter

**PROMPT — copy below:**

```
U-1.2: Update seed_location_match_labels.py for multi-suite.

FILE: backend/scripts/seed_location_match_labels.py

1. DEFAULT_FIXTURE → DEFAULT_FIXTURE_DIR = tests/fixtures/location_match_labels/

2. Add helpers:
   - list_suite_files(dir) → sorted *.json (skip README)
   - load_fixture_dir(dir, suite: str | None) → concatenate arrays;
     if suite set, only load {suite}.json OR entries where entry["suite"]==suite

3. CLI:
   --fixture PATH  (file OR directory; default = DEFAULT_FIXTURE_DIR)
   --suite NAME    (optional filter)

4. Usage docstring examples:
   ./venv/bin/python scripts/seed_location_match_labels.py
   ./venv/bin/python scripts/seed_location_match_labels.py --suite ucsf
   ./venv/bin/python scripts/seed_location_match_labels.py --fixture tests/fixtures/location_match_labels/synthetic.json

5. Keep upsert-by-label_id behavior.
```

---

# U-2 — Eval CLI: suite / project filters + per-suite report

- [x] **U-2.1** Filter + report in eval service + script

**PROMPT — copy below:**

```
U-2.1: Universalize eval_location_match.

FILES:
- backend/services/location_match_eval.py
- backend/scripts/eval_location_match.py

1. Prefer extracting shared loaders to backend/services/location_match_label_io.py:
   load_fixture, load_fixture_dir, validate_entry, list_suite_files, REQUIRED_FIELDS
   Update seed_location_match_labels.py imports to use that module.

2. location_match_eval.py:
   - load_eval_labels_from_json: accept path to file OR directory
   - load_eval_labels_from_db(session, *, suite=None, project_id=None)
   - EvalSummary.to_dict: add pass_rate_by_suite: dict[str, float]
   - evaluate_labels: compute pass_rate_by_suite from non-skipped results grouped by label.suite

3. eval_location_match.py CLI:
   --labels PATH (file or dir; default tests/fixtures/location_match_labels/)
   --suite NAME
   --project-id INT
   --from-db
   --min-iou --min-pass-rate --output (keep)
   Apply suite/project filters after load.
   Print per-suite pass rates before GATE line.

4. Do NOT default evidence/drawing IDs to UCSF values anywhere in these files.
```

---

# U-3 — Generalize verify script

- [ ] **U-3.1** Replace UCSF-only verify script

**PROMPT — copy below:**

```
U-3.1: Generalize verify_golden_location_match.py

1. RENAME
   backend/scripts/verify_golden_location_match.py
   → backend/scripts/verify_location_match_label.py

2. Behavior:
   - REQUIRED: --label-id OR (--evidence-id AND --master-drawing-id)
   - If --label-id: load LocationMatchLabel (or JSON suite file via --labels),
     use that row's evidence_id, master_drawing_id, expected_method, expected_match_status,
     master_bbox_json; compute IoU vs resolve_evidence_location result
   - Remove defaults 357 / 661 / 435
   - Keep --refresh-survey and --persist-match as optional flags
   - Exit 0 only if method+status match expectations and (if bbox area>0) IoU >= --min-iou (default 0.30)

3. Docstring example:
   ./venv/bin/python scripts/verify_location_match_label.py --label-id ucsf-435-ss-corridor --from-db
   ./venv/bin/python scripts/verify_location_match_label.py --evidence-id 10 --master-drawing-id 20

4. Grep repo for verify_golden_location_match and update references
   (Notes/inspection_upload_pipeline.md, any scripts/tests).
```

---

# U-4 — Export label helper (new projects)

- [ ] **U-4.1** Add export script

**PROMPT — copy below:**

```
U-4.1: Create backend/scripts/export_location_match_label.py

CLI (all required unless noted):
  --suite STR
  --label-id STR
  --project-id INT
  --master-drawing-id INT
  --evidence-id INT (optional)
  --inspection-run-id INT (optional)
  --expected-method STR
  --expected-match-status STR
  --bbox-x --bbox-y --bbox-width --bbox-height FLOAT
  --page INT default 1
  --evidence-kind STR
  --has-coordinate-signal/--has-station-signal/--has-reference-signal flags (store_true)
  --rotation-deg INT optional
  --notes STR optional
  --out PATH  (append to suite JSON array file, or create)

Behavior:
  Build one label dict matching seed schema (including suite).
  If --out exists and is JSON array: append (reject duplicate label_id).
  If --out missing: write new array [label].
  Print the JSON object to stdout.

No DB required for export (file-only).
```

---

# U-5 — Tests + anti-hardcode guard

- [ ] **U-5.1** Update seed/eval tests for suites

**PROMPT — copy below:**

```
U-5.1: Update tests for multi-suite labels.

FILES:
- backend/tests/test_location_match_labels_seed.py
- backend/tests/test_location_match_eval.py

1. test_location_match_labels_seed.py:
   - FIXTURE_DIR = fixtures/location_match_labels/
   - test_fixture_has_minimum_eval_rows: load ucsf.json; still assert 5 ucsf-* ids; each has suite=="ucsf"
   - test_synthetic_suite_exists: synthetic.json has >=2 rows, suite=="synthetic"
   - Rename test_golden_label_points_at_ucsf_evidence_and_master →
     test_ucsf_corridor_label_fields (keep assertions; this is suite data, not product invariant)
   - test_seed_location_match_labels_upserts: include "suite": "test" in _sample_label
   - Add test_seed_loads_directory_with_suite_filter

2. test_location_match_eval.py:
   - EvalLabel construction: include suite="test"
   - Add test_pass_rate_by_suite_in_summary (two labels different suites, mock evaluate_label)
```

---

- [ ] **U-5.2** Guard: no hard-coded UCSF IDs in match pipeline

**PROMPT — copy below:**

```
U-5.2: Add backend/tests/test_no_hardcoded_ucsf_match_ids.py

Scan these paths as text (fail test if forbidden literals appear):
  backend/ai/pipelines/location_match_orchestrator.py
  backend/ai/pipelines/drawing_location_resolver.py
  backend/ai/pipelines/survey_point_matcher.py
  backend/services/match_candidate_scope.py
  backend/services/location_match_eval.py

Forbidden literals:
  2131764.84
  6051541.82
  evidence_id=357
  master_drawing_id=661
  drawing_id=661
  run_id=435
  inspection_run_id=435

Allowed in: tests/fixtures/**, Notes/**, test_* files that load fixtures.

Assert scanned pipeline file contents do not contain those literals.
```

---

# U-6 — Docs

- [ ] **U-6.1** Retitle PR-G golden language

**PROMPT — copy below:**

```
U-6.1: Update Notes/inspection_upload_pipeline.md PR-G section only.

Replace "UCSF golden" / "Golden case: project 2, evidence 357..." framing with:
- Eval uses multi-suite labels under tests/fixtures/location_match_labels/
- ucsf.json is the first suite, not the only one
- New project = new <suite>.json via export_location_match_label.py + seed + eval

Update any commands that point at location_match_labels.json to the directory
or --suite ucsf.

Do not rewrite PR-A through PR-F.
```

---

# U-7 — Definition of done

- [ ] **U-7.1** Verify

**PROMPT — copy below:**

```
U-7.1: Run and fix until green:

cd backend
./venv/bin/python -m pytest \
  tests/test_location_match_labels_seed.py \
  tests/test_location_match_eval.py \
  tests/test_no_hardcoded_ucsf_match_ids.py \
  tests/test_location_match_orchestrator.py -q

./venv/bin/python scripts/seed_location_match_labels.py --suite synthetic
./venv/bin/python scripts/eval_location_match.py --labels tests/fixtures/location_match_labels --suite synthetic --min-iou 0.30

Confirm:
- [ ] location_match_labels.json root file gone
- [ ] ucsf.json + synthetic.json exist with suite field
- [ ] eval prints pass_rate_by_suite
- [ ] verify_golden_location_match.py gone; verify_location_match_label.py has no default 357/661
- [ ] matcher/orchestrator files have no hard-coded UCSF N/E or IDs
```

---

## Quick reference — adding a new project suite later

**PROMPT — copy below:**

```
Add location-match eval suite for project <SLUG>:

1. Index that project's drawings (survey points / text elements ready).
2. For each human pin, run:
   cd backend && ./venv/bin/python scripts/export_location_match_label.py \
     --suite <SLUG> --label-id <SLUG>-<case> --project-id <PID> \
     --master-drawing-id <DID> --evidence-id <EID> \
     --expected-method <method> --expected-match-status <status> \
     --bbox-x <x> --bbox-y <y> --bbox-width <w> --bbox-height <h> \
     --evidence-kind <kind> --out tests/fixtures/location_match_labels/<SLUG>.json
3. Seed: ./venv/bin/python scripts/seed_location_match_labels.py --suite <SLUG>
4. Eval: ./venv/bin/python scripts/eval_location_match.py --suite <SLUG>
5. Do not add project-specific branches to location_match_orchestrator.py
```
