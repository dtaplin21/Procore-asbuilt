# Symbol crop labeling (sheet digitization S-1)

Unlabeled crops are exported by:

```bash
cd backend
./venv/bin/python scripts/export_symbol_crops.py --drawing-id 1501
./venv/bin/python scripts/export_symbol_crops.py --drawing-id 661 --viewport-id plan
```

Crops start in `unknown/`. A root `manifest.csv` lists
`path,drawing_id,page,x0,y0,x1,y1,viewport_id` (fractional page coords).

## Classes v1 (sanitary)

| Folder | Meaning |
|--------|---------|
| `ssmh` | Sanitary sewer manhole symbol |
| `ssco` | Sanitary sewer cleanout / CO symbol |
| `callout_bubble` | Callout / revision bubble |
| `north_arrow` | North / view orientation arrow |
| `scale_bar` | Graphic scale bar |
| `other` | Recognizable symbol that is none of the above |
| `unknown` | Unlabeled export dump (sort out of here) |
| `holdout/` | **Never** use for training — keep for eval only |

## Labeling workflow

1. Export crops for golden sheets (aux C4.20 / `1501`, master `661`).
2. Sort PNGs from `unknown/` into the class folders above (or use Roboflow / CVAT and re-export into these folders).
3. Move a fixed holdout set into `holdout/` **before** training; do not train on it.
4. Target **≥200 crops per class** before training a detector (S-2).

Vision LLMs may help **classify** a crop into a folder name. Do **not** invent pixel boxes with an LLM — boxes come from this exporter / CV tools.

## Notes

- PNG crops and `manifest.csv` are gitignored; regenerate locally as needed.
- Prefer `--viewport-id plan` when the page is multi-scale so section/profile chrome is not mixed into plan-symbol training.
