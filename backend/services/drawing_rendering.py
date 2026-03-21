"""
PDF/image rendering service using PyMuPDF.

Standardizes all drawing page rendering logic for the workspace viewer.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import fitz  # PyMuPDF

from database import SessionLocal
from services.storage import (
    StorageService,
    build_drawing_render_storage_key,
    get_storage_file_size,
    open_storage_path,
    write_bytes_to_storage_key,
)

RENDER_DPI = 200
RENDER_MIME_TYPE = "image/png"


class DrawingRenderingService:
    def __init__(self, db):
        self.storage = StorageService(db)

    def render_drawing_pages(self, drawing_id: int) -> None:
        drawing = self.storage.get_drawing_by_id(drawing_id)
        if not drawing:
            raise ValueError(f"Drawing {drawing_id} not found")

        if not drawing.storage_key:
            raise ValueError(f"Drawing {drawing_id} has no storage_key")

        self.storage.set_drawing_processing_status(drawing_id, "processing", error=None)

        try:
            source_path = open_storage_path(drawing.storage_key)
            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            mime_type = (
                drawing.content_type
                or mimetypes.guess_type(str(source_path))[0]
                or ""
            )

            if mime_type == "application/pdf" or source_path.suffix.lower() == ".pdf":
                page_count = self._render_pdf(
                    drawing.project_id, drawing.id, source_path
                )
                self.storage.set_drawing_processing_status(
                    drawing_id, "ready", page_count=page_count
                )
            elif mime_type.startswith("image/"):
                self._register_existing_image_as_rendition(
                    drawing.project_id,
                    drawing.id,
                    drawing.storage_key,
                    source_path,
                    mime_type,
                )
                self.storage.set_drawing_processing_status(
                    drawing_id, "ready", page_count=1
                )
            else:
                raise ValueError(f"Unsupported drawing mime type: {mime_type}")

        except Exception as exc:
            self.storage.set_drawing_processing_status(
                drawing_id,
                "failed",
                error=str(exc),
            )
            raise

    def _render_pdf(
        self, project_id: int, drawing_id: int, source_path: Path
    ) -> int:
        doc = fitz.open(source_path)
        try:
            page_count = doc.page_count
            for zero_based_index in range(page_count):
                page = doc.load_page(zero_based_index)
                pix = page.get_pixmap(dpi=RENDER_DPI, alpha=False)

                png_bytes = pix.tobytes("png")
                page_number = zero_based_index + 1
                storage_key = build_drawing_render_storage_key(
                    project_id, drawing_id, page_number
                )
                write_bytes_to_storage_key(storage_key, png_bytes)

                self.storage.upsert_drawing_rendition(
                    drawing_id=drawing_id,
                    page_number=page_number,
                    image_storage_key=storage_key,
                    mime_type=RENDER_MIME_TYPE,
                    width_px=pix.width,
                    height_px=pix.height,
                    file_size=get_storage_file_size(storage_key),
                    render_status="ready",
                )

            return page_count
        finally:
            doc.close()

    def _register_existing_image_as_rendition(
        self,
        project_id: int,
        drawing_id: int,
        storage_key: str,
        source_path: Path,
        mime_type: str,
    ) -> None:
        """Reuse original image as page 1 viewer asset if already renderable."""
        import cv2

        img = cv2.imread(str(source_path))
        width_px = int(img.shape[1]) if img is not None else None
        height_px = int(img.shape[0]) if img is not None else None
        file_size = source_path.stat().st_size if source_path.exists() else None

        self.storage.upsert_drawing_rendition(
            drawing_id=drawing_id,
            page_number=1,
            image_storage_key=storage_key,
            mime_type=mime_type,
            width_px=width_px,
            height_px=height_px,
            file_size=file_size,
            render_status="ready",
        )


def run_render_drawing_job(drawing_id: int) -> None:
    db = SessionLocal()
    try:
        service = DrawingRenderingService(db)
        service.render_drawing_pages(drawing_id)
    finally:
        db.close()
