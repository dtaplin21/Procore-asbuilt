#!/usr/bin/env python3
"""Compare persisted native_pdf tokens vs display-frame extraction (rotation fix)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import fitz  # noqa: E402

from ai.pipelines.native_pdf_display_frame import (  # noqa: E402
    frame_agreement,
    native_words_display_fractional,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("export_json", type=Path, help="export_drawing_index_json output")
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args()

    data = json.loads(args.export_json.read_text())
    elements = data.get("drawing_text_elements") or []
    persisted_native = [t for t in elements if t.get("source") == "native_pdf" and t.get("page") == args.page]
    docai = [t for t in elements if t.get("source") == "document_ai" and t.get("page") == args.page]

    doc = fitz.open(str(args.pdf))
    page = doc.load_page(args.page - 1)
    fixed_native = native_words_display_fractional(page)
    doc.close()

    before = frame_agreement(persisted_native, docai)
    after = frame_agreement(fixed_native, docai)
    print("persisted native_pdf vs Document AI:", before)
    print("display-frame native vs Document AI :", after)

    tick = [w for w in fixed_native if w.text in ("0'", "4'", "10'", "20'", "40'")]
    for word in sorted(tick, key=lambda w: w.cx):
        print(f"  {word.text:>4} -> x={word.cx:.4f} y={word.cy:.4f}")


if __name__ == "__main__":
    main()
