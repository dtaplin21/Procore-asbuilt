#!/usr/bin/env python3
"""Validate line-local scale resolution on a PDF + optional index export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import fitz  # noqa: E402

from ai.pipelines.native_pdf_display_frame import native_words_display_fractional  # noqa: E402
from ai.pipelines.scale_resolution import DisplayScaleWord, resolve_scale, resolve_scale_from_sources  # noqa: E402


def _from_export_token(t: dict) -> DisplayScaleWord:
    b = t["bbox_json"]
    return DisplayScaleWord(
        text=str(t["text"]),
        x0=float(b["x0"]),
        y0=float(b["y0"]),
        x1=float(b["x1"]),
        y1=float(b["y1"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("export_json", type=Path, nargs="?", default=None)
    args = parser.parse_args()

    doc = fitz.open(str(args.pdf))
    try:
        page = doc[0]
        page_w_in = page.rect.width / 72.0
        native = native_words_display_fractional(page)
    finally:
        doc.close()

    r1 = resolve_scale(native, page_w_in)
    print("native display frame ->", r1["status"], "|", r1.get("reason"))
    if r1.get("scale_json"):
        print("  scale:", r1["scale_json"].get("raw_text"), r1["scale_json"].get("real_feet_per_paper_inch"))

    if args.export_json and args.export_json.is_file():
        data = json.loads(args.export_json.read_text())
        elements = data.get("drawing_text_elements") or []
        docai = [_from_export_token(t) for t in elements if t.get("source") == "document_ai"]
        r2 = resolve_scale(docai, page_w_in)
        print("Document AI only     ->", r2["status"], "|", r2.get("reason"))
        r3 = resolve_scale_from_sources([native, docai], page_w_in)
        print("native + Document AI ->", r3["status"], "|", r3.get("reason"))


if __name__ == "__main__":
    main()
