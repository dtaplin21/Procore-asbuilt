#!/usr/bin/env python3
"""Run Document AI batch OCR on a local PDF (live GCP — integration only).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/run_document_ai_batch.py --pdf /path/to/master.pdf
    ./venv/bin/python scripts/run_document_ai_batch.py --pdf master.pdf --timeout 7200

Requires Phase 0 env vars and ``document_ai_configured()`` true.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from ai.pipelines.document_ai_batch import batch_extract_words_from_pdf  # noqa: E402
from config import document_ai_configured  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Document AI batch OCR on a PDF file.")
    parser.add_argument("--pdf", type=Path, required=True, help="Local PDF path")
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600.0,
        help="Max seconds to wait for batch LRO (default 3600)",
    )
    args = parser.parse_args()

    if not document_ai_configured():
        print(
            "Document AI not configured. Set GOOGLE_CLOUD_PROJECT, DOCUMENT_AI_PROCESSOR_ID, "
            "and GCS bucket env vars (see Notes/ai google implementation.md).",
            file=sys.stderr,
        )
        return 1

    if not args.pdf.is_file():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    try:
        result = batch_extract_words_from_pdf(args.pdf, timeout_seconds=args.timeout)
    except ImportError:
        print("Install google-cloud-documentai and google-cloud-storage.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Batch OCR failed: {exc}", file=sys.stderr)
        return 1

    print(f"input:  {result.input_gcs_uri}")
    print(f"output: {result.output_gcs_prefix}")
    print(f"json shards: {len(result.output_blob_names)}")
    print(f"tokens: {len(result.words)}")
    for word in result.words[:20]:
        print(f"  p{word.page_index} {word.text!r} conf={word.ocr_confidence:.2f}")
    if len(result.words) > 20:
        print(f"  ... ({len(result.words) - 20} more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
