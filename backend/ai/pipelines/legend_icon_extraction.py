"""Raster legend icon crops from OCR row geometry (reference templates for symbols/lines).

Legend line-item labels on many CAD masters are not in the native PDF text layer;
row boundaries come from indexed OCR/Document AI tokens or a one-off Tesseract
pass on a legend crop. Icon regions are everything left of the label column.

See ``Notes/pdf poly line.md`` Step 2 — complements vector ``legend_line_swatch``.
"""

from __future__ import annotations

import dataclasses
import json
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import fitz
from PIL import Image

from ai.pipelines.fractional_coords import clamp_fractional_bbox
from ai.pipelines.legend_line_row_builder import LegendLineRow, cluster_legend_line_rows
from ai.pipelines.ocr_engine import ocr_image_tesseract, tesseract_is_available
from models.drawing_text_element import DrawingTextElement

LegendIconSource = Literal["indexed_tokens", "tesseract_crop"]

_DEFAULT_ZOOM = 2.0
_ROW_PAD_PX = 8
_OCR_CONF_THRESHOLD = 30
_ROW_GAP_TOLERANCE_PX = 12
_COLUMN_GAP_PX = 80


@dataclasses.dataclass(frozen=True)
class LegendIconEntry:
    row_id: int
    label_text: str
    icon_crop_path: str
    icon_fractional_bbox: tuple[float, float, float, float]
    label_fractional_bbox: tuple[float, float, float, float]
    source: LegendIconSource


def parse_legend_bbox_arg(value: str) -> tuple[float, float, float, float]:
    """Parse ``x0,y0,x1,y1`` fractional bounds from CLI."""
    parts = [float(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("legend bbox must be four comma-separated fractions")
    return clamp_fractional_bbox((parts[0], parts[1], parts[2], parts[3]))


def render_pdf_page_image(
    pdf_path: str | Path,
    *,
    page: int = 1,
    zoom: float = _DEFAULT_ZOOM,
) -> Image.Image:
    """Render one page to RGB PIL (PyMuPDF applies page rotation)."""
    doc = fitz.open(str(pdf_path))
    try:
        page_index = max(page - 1, 0)
        if page_index >= doc.page_count:
            page_index = 0
        pdf_page = doc.load_page(page_index)
        matrix = fitz.Matrix(zoom, zoom)
        pix = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def _frac_bbox_to_pixel_box(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    return (
        int(x0 * width),
        int(y0 * height),
        int(x1 * width),
        int(y1 * height),
    )


def _pad_row_frac_bbox(
    bbox: tuple[float, float, float, float],
    *,
    pad_y_px: int,
    page_height: int,
) -> tuple[float, float, float, float]:
    if page_height <= 0:
        return bbox
    pad = pad_y_px / float(page_height)
    x0, y0, x1, y1 = bbox
    return clamp_fractional_bbox((x0, y0 - pad, x1, y1 + pad))


def legend_icon_entries_from_rows(
    page_image: Image.Image,
    rows: list[LegendLineRow],
    output_dir: str | Path,
    *,
    source: LegendIconSource = "indexed_tokens",
    row_pad_px: int = _ROW_PAD_PX,
) -> list[LegendIconEntry]:
    """Write one PNG crop per row using ``swatch_bbox`` / ``label_bbox`` on the full page."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    width, height = page_image.size
    entries: list[LegendIconEntry] = []

    for index, row in enumerate(rows):
        row_icon = _pad_row_frac_bbox(
            row.swatch_bbox,
            pad_y_px=row_pad_px,
            page_height=height,
        )
        box = _frac_bbox_to_pixel_box(row_icon, width, height)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        icon_crop = page_image.crop(box)
        icon_path = out / f"legend_icon_{index:02d}.png"
        icon_crop.save(icon_path)
        entries.append(
            LegendIconEntry(
                row_id=index,
                label_text=row.text,
                icon_crop_path=str(icon_path),
                icon_fractional_bbox=row_icon,
                label_fractional_bbox=row.label_bbox,
                source=source,
            )
        )

    return entries


def _tesseract_words_on_image(
    image: Image.Image,
    *,
    ocr_conf_threshold: int = _OCR_CONF_THRESHOLD,
) -> list[dict[str, Any]]:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    words, _w, _h = ocr_image_tesseract(image_bytes=buffer.getvalue(), page_index=0)
    out: list[dict[str, Any]] = []
    for word in words:
        conf_pct = int(round(float(word.ocr_confidence or 0.0) * 100.0))
        if conf_pct < ocr_conf_threshold:
            continue
        bbox = word.bbox
        x0 = float(bbox.x)
        y0 = float(bbox.y)
        x1 = x0 + float(bbox.width)
        y1 = y0 + float(bbox.height)
        out.append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": str(word.text).strip(),
                "conf": conf_pct,
            }
        )
    return out


def _select_main_text_column_px(
    words: list[dict[str, Any]],
    *,
    column_gap_px: int = _COLUMN_GAP_PX,
) -> tuple[int, int]:
    """Return ``(text_col_x_min, text_col_x_max)`` in crop pixel space."""
    if not words:
        return 0, 0
    by_x = sorted(words, key=lambda w: w["x0"])
    columns: list[list[dict[str, Any]]] = []
    for word in by_x:
        if columns and word["x0"] - columns[-1][-1]["x0"] <= column_gap_px:
            columns[-1].append(word)
        else:
            columns.append([word])
    main_column = max(columns, key=len)
    text_col_x = int(min(w["x0"] for w in main_column))
    text_col_x_max = int(max(w["x1"] for w in main_column) + column_gap_px)
    return text_col_x, text_col_x_max


def _cluster_pixel_rows(
    label_words: list[dict[str, Any]],
    *,
    row_gap_tolerance_px: int = _ROW_GAP_TOLERANCE_PX,
) -> list[dict[str, Any]]:
    label_words = sorted(label_words, key=lambda w: w["y0"])
    rows: list[dict[str, Any]] = []
    for word in label_words:
        if rows and word["y0"] - rows[-1]["y1"] <= row_gap_tolerance_px:
            rows[-1]["words"].append(word)
            rows[-1]["y0"] = min(rows[-1]["y0"], word["y0"])
            rows[-1]["y1"] = max(rows[-1]["y1"], word["y1"])
        else:
            rows.append({"y0": word["y0"], "y1": word["y1"], "words": [word]})
    return rows


def extract_legend_icons_tesseract_crop(
    pdf_path: str | Path,
    *,
    page: int = 1,
    legend_bbox_fractional: tuple[float, float, float, float],
    output_dir: str | Path,
    text_column_x_min_frac: float | None = None,
    zoom: float = _DEFAULT_ZOOM,
    ocr_conf_threshold: int = _OCR_CONF_THRESHOLD,
    row_gap_tolerance_px: int = _ROW_GAP_TOLERANCE_PX,
    column_gap_px: int = _COLUMN_GAP_PX,
) -> list[LegendIconEntry]:
    """OCR a legend crop and emit icon PNGs (standalone validation path)."""
    if not tesseract_is_available():
        raise RuntimeError("Tesseract is not available for legend crop OCR")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    full_img = render_pdf_page_image(pdf_path, page=page, zoom=zoom)
    width, height = full_img.size
    lx0, ly0, lx1, ly1 = clamp_fractional_bbox(legend_bbox_fractional)
    crop_box = _frac_bbox_to_pixel_box((lx0, ly0, lx1, ly1), width, height)
    legend_img = full_img.crop(crop_box)
    crop_w, crop_h = legend_img.size

    words = _tesseract_words_on_image(legend_img, ocr_conf_threshold=ocr_conf_threshold)
    if not words:
        return []

    if text_column_x_min_frac is None:
        text_col_x, text_col_x_max = _select_main_text_column_px(words, column_gap_px=column_gap_px)
    else:
        text_col_x = int(text_column_x_min_frac * crop_w)
        text_col_x_max = crop_w

    label_words = [w for w in words if text_col_x - 5 <= w["x0"] <= text_col_x_max]
    pixel_rows = _cluster_pixel_rows(label_words, row_gap_tolerance_px=row_gap_tolerance_px)

    entries: list[LegendIconEntry] = []
    for index, row in enumerate(pixel_rows):
        label_text = " ".join(
            w["text"] for w in sorted(row["words"], key=lambda w: w["x0"])
        )
        row_y0 = max(0, int(row["y0"]) - _ROW_PAD_PX)
        row_y1 = min(crop_h, int(row["y1"]) + _ROW_PAD_PX)
        icon_crop = legend_img.crop((0, row_y0, text_col_x, row_y1))
        icon_path = out / f"legend_icon_{index:02d}.png"
        icon_crop.save(icon_path)

        label_x0 = lx0 + (min(w["x0"] for w in row["words"]) / crop_w) * (lx1 - lx0)
        label_x1 = lx0 + (max(w["x1"] for w in row["words"]) / crop_w) * (lx1 - lx0)
        label_y0 = ly0 + (row_y0 / crop_h) * (ly1 - ly0)
        label_y1 = ly0 + (row_y1 / crop_h) * (ly1 - ly0)
        icon_x1 = lx0 + (text_col_x / crop_w) * (lx1 - lx0)

        entries.append(
            LegendIconEntry(
                row_id=index,
                label_text=label_text,
                icon_crop_path=str(icon_path),
                icon_fractional_bbox=(
                    lx0,
                    label_y0,
                    icon_x1,
                    label_y1,
                ),
                label_fractional_bbox=(label_x0, label_y0, label_x1, label_y1),
                source="tesseract_crop",
            )
        )

    return entries


def extract_legend_icons_from_indexed_tokens(
    pdf_path: str | Path,
    elements: list[DrawingTextElement],
    *,
    page: int = 1,
    legend_bbox_fractional: tuple[float, float, float, float] | None = None,
    output_dir: str | Path,
    zoom: float = _DEFAULT_ZOOM,
) -> list[LegendIconEntry]:
    """Build icon crops from ``DrawingTextElement`` rows (Document AI / Tesseract index)."""
    legend_rect = (
        clamp_fractional_bbox(legend_bbox_fractional)
        if legend_bbox_fractional is not None
        else None
    )
    rows = cluster_legend_line_rows(elements, legend_rect=legend_rect)
    if not rows:
        return []

    page_image = render_pdf_page_image(pdf_path, page=page, zoom=zoom)
    return legend_icon_entries_from_rows(
        page_image,
        rows,
        output_dir,
        source="indexed_tokens",
    )


def extract_legend_icons(
    pdf_path: str | Path,
    *,
    page: int = 1,
    legend_bbox_fractional: tuple[float, float, float, float],
    output_dir: str | Path,
    elements: list[DrawingTextElement] | None = None,
    prefer_indexed: bool = True,
    **tesseract_kwargs: Any,
) -> list[LegendIconEntry]:
    """Extract legend icon PNGs; prefer indexed tokens when rows exist."""
    if prefer_indexed and elements:
        indexed = extract_legend_icons_from_indexed_tokens(
            pdf_path,
            elements,
            page=page,
            legend_bbox_fractional=legend_bbox_fractional,
            output_dir=output_dir,
        )
        if indexed:
            return indexed

    return extract_legend_icons_tesseract_crop(
        pdf_path,
        page=page,
        legend_bbox_fractional=legend_bbox_fractional,
        output_dir=output_dir,
        **tesseract_kwargs,
    )


def legend_icon_entries_to_manifest(entries: list[LegendIconEntry]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(entry) for entry in entries]


def write_legend_icon_manifest(
    entries: list[LegendIconEntry],
    output_dir: str | Path,
    *,
    filename: str = "legend_manifest.json",
) -> Path:
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(legend_icon_entries_to_manifest(entries), indent=2), encoding="utf-8")
    return path
