# Location match eval suites

- One JSON array file per suite
- Required fields: suite, label_id, project_id, master_drawing_id,
  master_bbox_json, expected_method, expected_match_status,
  has_coordinate_signal, has_station_signal, has_reference_signal, evidence_kind
- Optional: evidence_id, inspection_run_id, evidence_fixture_path, rotation_deg, notes
- Add a new project by adding `<slug>.json` — do not hard-code IDs in matchers
