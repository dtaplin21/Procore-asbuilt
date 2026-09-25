#!/usr/bin/env python3
"""Create (or list) a Document AI OCR processor for master drawing batch OCR.

One-time per GCP project + location. Save the printed processor resource name as
``DOCUMENT_AI_PROCESSOR_ID`` in ``backend/.env`` (see Notes/ai google implementation.md).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/create_document_ai_processor.py
    ./venv/bin/python scripts/create_document_ai_processor.py --list
    ./venv/bin/python scripts/create_document_ai_processor.py --project-id my-proj --location us

Requires Application Default Credentials (``gcloud auth application-default login``)
or ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at a service account with permission
to create processors in the project.
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

from ai.pipelines.document_ai_client import document_processor_client  # noqa: E402
from config import settings  # noqa: E402

DEFAULT_DISPLAY_NAME = "procore-integrator-master-ocr"
PROCESSOR_TYPE = "OCR_PROCESSOR"


def list_processors(*, project_id: str, location: str) -> None:
    client = document_processor_client(location)
    parent = client.common_location_path(project_id, location)
    print(f"Processors in {parent}:\n")
    found = False
    for proc in client.list_processors(parent=parent):
        found = True
        print(f"  name:         {proc.name}")
        print(f"  display_name: {proc.display_name}")
        print(f"  type:         {proc.type_}")
        print(f"  state:        {proc.state.name if proc.state else '?'}")
        print()
    if not found:
        print("  (none)")


def create_processor(
    *,
    project_id: str,
    location: str,
    display_name: str,
) -> str:
    from google.cloud import documentai

    client = document_processor_client(location)
    parent = client.common_location_path(project_id, location)
    processor = client.create_processor(
        parent=parent,
        processor=documentai.Processor(
            display_name=display_name,
            type_=PROCESSOR_TYPE,
        ),
    )
    return processor.name


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or list Document AI OCR processors.")
    parser.add_argument(
        "--project-id",
        default=settings.google_cloud_project,
        help="GCP project id (default: GOOGLE_CLOUD_PROJECT from .env)",
    )
    parser.add_argument(
        "--location",
        default=settings.document_ai_location,
        choices=("us", "eu"),
        help="Document AI location (default: DOCUMENT_AI_LOCATION)",
    )
    parser.add_argument(
        "--display-name",
        default=DEFAULT_DISPLAY_NAME,
        help=f"Processor display name (default: {DEFAULT_DISPLAY_NAME})",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing processors instead of creating one",
    )
    args = parser.parse_args()

    if not args.project_id:
        print(
            "Missing project id. Set GOOGLE_CLOUD_PROJECT in backend/.env or pass --project-id.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.list:
            list_processors(project_id=args.project_id, location=args.location)
            return 0

        name = create_processor(
            project_id=args.project_id,
            location=args.location,
            display_name=args.display_name,
        )
    except ImportError:
        print(
            "Install google-cloud-documentai: pip install google-cloud-documentai",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Document AI API error: {exc}", file=sys.stderr)
        print(
            "If a processor already exists, run with --list and set DOCUMENT_AI_PROCESSOR_ID "
            "to the existing resource name.",
            file=sys.stderr,
        )
        return 1

    print("Created processor.")
    print(f"  DOCUMENT_AI_PROCESSOR_ID={name}")
    print()
    print("Add that line to backend/.env and Render/API secrets (Phase 0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
