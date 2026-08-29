# Digitization golden page renditions

Local PNG exports of UCSF sheets used by `Notes/sheet_digitization_plan.md`
(Phase PRE-2+). Generated at **150 DPI** via PyMuPDF (digitization PRE-2
convention; `ocr_engine` default is 200).

| File | Drawing | What it is |
|------|---------|------------|
| `master_661_page1.png` | `661` | Campus master (U2.C4.00) — single primary **plan** scale |
| `aux_c420_page1.png` | `1501` | C4.20 sanitary install — **multi-scale** (plan + section on one sheet) |

Drawing IDs match `scripts/seed_master_registration_controls.py`
(`MASTER_ID=661`, `AUX_ID=1501`).

## Regenerate (do not commit large PNGs)

`*.png` in this folder is gitignored. Re-export anytime from `backend/`:

```bash
./venv/bin/python scripts/export_drawing_page_png.py --drawing-id 661 --page 1 \
  --out tests/fixtures/digitization/master_661_page1.png

./venv/bin/python scripts/export_drawing_page_png.py --drawing-id 1501 --page 1 \
  --out tests/fixtures/digitization/aux_c420_page1.png
```

## If export fails (PDF missing)

Source PDFs live under `backend/uploads/` via each drawing’s `storage_key`, e.g.:

- `uploads/projects/2/drawings/…_Master.pdf`
- `uploads/projects/2/linked_drawings/…_U1.C4.20_….pdf`

Ensure the drawing rows exist in the DB and the files are on disk, then re-run
the commands above. For manual viewport picking without fixtures, point
`pick_fractional_point.py` at those uploads paths or at a freshly exported PNG.
