/**
 * Converts raw pointer-drag coordinates from the draw canvas (PR3) into
 * normalized DrawingRegionGeometry ready for createDrawingRegion /
 * updateDrawingRegion (PR2). Coordinates are normalized 0–1 — not pixel
 * x/y/width/pageWidth columns.
 */

import type {
  DrawingRegionGeometry,
  DrawingRegionRectGeometry,
} from "@/lib/drawing-regions/types";

export interface PointerPoint {
  x: number;
  y: number;
}

export interface PolygonRegionDraft {
  /** Axis-aligned hit box (same role as Roof Area in sample_drawing_regions.json). */
  geometry: DrawingRegionRectGeometry;
  polygon_points: Array<[number, number]>;
}

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function normalizePoint(
  point: PointerPoint,
  pageWidth: number,
  pageHeight: number,
): [number, number] {
  if (pageWidth <= 0 || pageHeight <= 0) {
    throw new Error("Page dimensions must be positive.");
  }
  return [clamp01(point.x / pageWidth), clamp01(point.y / pageHeight)];
}

function normalizeRect(
  x: number,
  y: number,
  width: number,
  height: number,
  pageWidth: number,
  pageHeight: number,
): DrawingRegionRectGeometry {
  const nx = clamp01(x / pageWidth);
  const ny = clamp01(y / pageHeight);
  const nw = Math.max(0, Math.min(1 - nx, width / pageWidth));
  const nh = Math.max(0, Math.min(1 - ny, height / pageHeight));
  return { type: "rect", x: nx, y: ny, width: nw, height: nh };
}

/**
 * Build a rectangular region from two drag-corner points in on-screen pixel
 * space plus the rendered image's natural pixel dimensions.
 */
export function rectFromDragPoints(
  start: PointerPoint,
  end: PointerPoint,
  pageWidth: number,
  pageHeight: number,
): DrawingRegionRectGeometry {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  return normalizeRect(x, y, width, height, pageWidth, pageHeight);
}

/**
 * Build a polygon region from clicked points. Returns a rect hit-box geometry
 * plus normalized polygon_points (backend stores both for bbox fallback).
 */
export function polygonFromPoints(
  points: PointerPoint[],
  pageWidth: number,
  pageHeight: number,
): PolygonRegionDraft {
  if (points.length < 3) {
    throw new Error("A polygon region needs at least 3 points.");
  }

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  const width = Math.max(...xs) - x;
  const height = Math.max(...ys) - y;

  return {
    geometry: normalizeRect(x, y, width, height, pageWidth, pageHeight),
    polygon_points: points.map((p) => normalizePoint(p, pageWidth, pageHeight)),
  };
}

/** Convert normalized region geometry to fractional [x0, y0, x1, y1]. */
export function geometryToFractionalBbox(
  geometry: DrawingRegionGeometry,
): [number, number, number, number] {
  if (geometry.type === "rect") {
    return [
      geometry.x,
      geometry.y,
      geometry.x + geometry.width,
      geometry.y + geometry.height,
    ];
  }

  const xs = geometry.points.map(([x]) => x);
  const ys = geometry.points.map(([, y]) => y);
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  const x1 = Math.max(...xs);
  const y1 = Math.max(...ys);
  return [x0, y0, x1, y1];
}

/** Convert normalized polygon points to the same space (pass-through helper for SVG). */
export function polygonPointsToFractional(
  points: Array<[number, number]>,
): Array<[number, number]> {
  return points.map(([x, y]) => [clamp01(x), clamp01(y)]);
}

export function validateGeometry(
  geometry: DrawingRegionGeometry,
  polygonPoints?: Array<[number, number]> | null,
): string | null {
  if (geometry.type === "rect") {
    if (geometry.width <= 0 || geometry.height <= 0) {
      return "Region must have a positive width and height.";
    }
    for (const [key, value] of Object.entries(geometry)) {
      if (key === "type") continue;
      if (typeof value !== "number" || value < 0 || value > 1) {
        return "Rect geometry coordinates must be normalized between 0 and 1.";
      }
    }
  } else if (geometry.type === "polygon") {
    if (geometry.points.length < 3) {
      return "A polygon region needs at least 3 points.";
    }
    for (const [x, y] of geometry.points) {
      if (x < 0 || x > 1 || y < 0 || y > 1) {
        return "Polygon points must be normalized between 0 and 1.";
      }
    }
  } else {
    return "geometry.type must be 'rect' or 'polygon'.";
  }

  if (polygonPoints != null && polygonPoints.length > 0 && polygonPoints.length < 3) {
    return "polygon_points needs at least 3 points.";
  }

  return null;
}
