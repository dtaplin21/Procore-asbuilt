# Location match eval suites

- One JSON array file per suite
- Required fields: suite, label_id, project_id, master_drawing_id,
  master_bbox_json, expected_method, expected_match_status,
  has_coordinate_signal, has_station_signal, has_reference_signal, evidence_kind
- Optional: evidence_id, inspection_run_id, evidence_fixture_path, rotation_deg,
  notes, master_scope_geometry_json

## Annotation guide

- **Do not seed synthetic survey points** (e.g. `pre2_baseline_seed`) for eval — coordinate
  lookup requires `auto_index`/`lazy_match` rows with real OCR label bboxes. Use
  `scripts/remove_baseline_survey_seeds.py` to clean stale seeds.
- **Utility run inspections** (sewer, water, conduit, lateral): mark a **polyline**
  along the exact scoped line on the master drawing. Set `master_scope_geometry_json`
  with `"type": "polyline"`, normalized `points` (0–1), and `"scope_kind": "utility_line"`.
  Keep `master_bbox_json` as a tight rect envelope for backward-compatible IoU checks.
- **Area inspections** (room, zone, parking lot): use **rect** or **polygon** in
  `master_scope_geometry_json` when precise scope matters; rect-only labels remain valid.
- **Do not label by sheet number** — ground truth is always geometry on the master drawing,
  never sheet-reference placement.

Add a new project by adding `<slug>.json` — do not hard-code IDs in matchers.
