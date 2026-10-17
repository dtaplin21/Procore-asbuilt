import type {
  DrawingDiffRegion,
  NormalizedPoint,
  NormalizedRect,
} from "@/types/drawing_workspace";
import type {
  PixelPoint,
  PixelRect,
  ResolvedOverlayRegion,
  ViewerSize,
} from "@/lib/drawing-overlays/overlay-types";

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function normalizeRect(rect: NormalizedRect): NormalizedRect {
  return {
    x: clamp01(rect.x),
    y: clamp01(rect.y),
    width: Math.max(0, Math.min(1 - clamp01(rect.x), rect.width)),
    height: Math.max(0, Math.min(1 - clamp01(rect.y), rect.height)),
  };
}

export function normalizePoints(points: NormalizedPoint[]): NormalizedPoint[] {
  return points.map((point) => ({
    x: clamp01(point.x),
    y: clamp01(point.y),
  }));
}

function normalizeSegments(
  segments: [NormalizedPoint, NormalizedPoint][]
): [NormalizedPoint, NormalizedPoint][] {
  return segments.map(([start, end]) => [normalizePoints([start])[0], normalizePoints([end])[0]]);
}

export function resolveOverlayRegion(region: DrawingDiffRegion): ResolvedOverlayRegion | null {
  if (region.shapeType === "line_segments" && region.segments && region.segments.length >= 1) {
    return {
      kind: "line_segments",
      segments: normalizeSegments(region.segments),
      source: region,
    };
  }

  if (region.shapeType === "polyline" && region.points && region.points.length >= 2) {
    const segments: [NormalizedPoint, NormalizedPoint][] = [];
    const points = normalizePoints(region.points);
    for (let index = 0; index < points.length - 1; index += 1) {
      segments.push([points[index], points[index + 1]]);
    }
    if (segments.length >= 1) {
      return {
        kind: "line_segments",
        segments,
        source: region,
      };
    }
  }

  if (region.shapeType === "polygon" && region.points && region.points.length >= 3) {
    return {
      kind: "polygon",
      points: normalizePoints(region.points),
      source: region,
    };
  }

  if (region.shapeType === "rect" && region.rect) {
    return {
      kind: "rect",
      rect: normalizeRect(region.rect),
      source: region,
    };
  }

  if (region.bbox) {
    return {
      kind: "rect",
      rect: normalizeRect({
        x: region.bbox.x,
        y: region.bbox.y,
        width: region.bbox.width,
        height: region.bbox.height,
      }),
      source: region,
    };
  }

  return null;
}

export function normalizedRectToPixels(
  rect: NormalizedRect,
  viewer: ViewerSize
): PixelRect {
  return {
    x: rect.x * viewer.width,
    y: rect.y * viewer.height,
    width: rect.width * viewer.width,
    height: rect.height * viewer.height,
  };
}

export function normalizedPointsToPixels(
  points: NormalizedPoint[],
  viewer: ViewerSize
): PixelPoint[] {
  return points.map((point) => ({
    x: point.x * viewer.width,
    y: point.y * viewer.height,
  }));
}

export function polygonPointsToSvgString(points: PixelPoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}
