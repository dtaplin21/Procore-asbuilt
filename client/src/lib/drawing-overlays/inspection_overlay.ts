import type { DrawingOverlay } from "@shared/schema";

import type {
  DrawingDiff,
  DrawingDiffRegion,
  NormalizedPoint,
  NormalizedRect,
  ReviewBadgeTone,
} from "@/types/drawing_workspace";
import type { OverlayRegion, OverlayRegionKind } from "@/lib/drawing-overlays/overlay-types";

export type OverlayInspectionTone = ReviewBadgeTone | "neutral";

const OVERLAY_PALETTE: Record<
  OverlayInspectionTone,
  { stroke: string; fill: string; strokeMuted: string; fillMuted: string }
> = {
  changed: {
    stroke: "#d97706",
    fill: "rgba(217, 119, 6, 0.14)",
    strokeMuted: "#b45309",
    fillMuted: "rgba(180, 83, 9, 0.18)",
  },
  passed: {
    stroke: "#16a34a",
    fill: "rgba(22, 163, 74, 0.12)",
    strokeMuted: "#15803d",
    fillMuted: "rgba(21, 128, 61, 0.16)",
  },
  failed: {
    stroke: "#dc2626",
    fill: "rgba(220, 38, 38, 0.14)",
    strokeMuted: "#b91c1c",
    fillMuted: "rgba(185, 28, 28, 0.18)",
  },
  neutral: {
    stroke: "#d97706",
    fill: "rgba(217, 119, 6, 0.12)",
    strokeMuted: "#b45309",
    fillMuted: "rgba(180, 83, 9, 0.15)",
  },
};

export function overlayColorsForTone(tone: OverlayInspectionTone, selected: boolean) {
  const p = OVERLAY_PALETTE[tone];
  const strokeWidth = selected ? 3 : 2;
  return {
    stroke: selected ? p.strokeMuted : p.stroke,
    fill: selected ? p.fillMuted : p.fill,
    strokeWidth,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readInspectionRunId(overlay: DrawingOverlay): number | null {
  const wire = overlay as DrawingOverlay & { inspectionRunId?: number | null };
  return overlay.inspection_run_id ?? wire.inspectionRunId ?? null;
}

function readDiffId(overlay: DrawingOverlay): number | null {
  const wire = overlay as DrawingOverlay & { diffId?: number | null };
  return overlay.diff_id ?? wire.diffId ?? null;
}

function readLabel(geometry: Record<string, unknown>, meta: Record<string, unknown> | null): string | null {
  const fromGeometry = geometry.label;
  if (typeof fromGeometry === "string" && fromGeometry.trim()) {
    return fromGeometry.trim();
  }
  if (meta) {
    const fromMeta = meta.label;
    if (typeof fromMeta === "string" && fromMeta.trim()) {
      return fromMeta.trim();
    }
  }
  return null;
}

function readSeverity(
  overlay: DrawingOverlay,
  meta: Record<string, unknown> | null
): string {
  const wire = overlay as DrawingOverlay & { severity?: string | null };
  if (typeof wire.severity === "string" && wire.severity.trim()) {
    return wire.severity.trim();
  }
  if (meta) {
    const fromMeta = meta.severity;
    if (typeof fromMeta === "string" && fromMeta.trim()) {
      return fromMeta.trim();
    }
  }
  const status = overlay.status?.toLowerCase();
  if (status === "fail") return "high";
  if (status === "pass") return "low";
  return "info";
}

function overlayStatusToReviewBadge(status: string | null | undefined): ReviewBadgeTone {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "pass") return "passed";
  if (normalized === "fail") return "failed";
  return "changed";
}

function parseNormalizedPoint(value: unknown): NormalizedPoint | null {
  if (Array.isArray(value) && value.length >= 2) {
    const x = readNumber(value[0]);
    const y = readNumber(value[1]);
    if (x == null || y == null) return null;
    return { x, y };
  }
  if (isRecord(value)) {
    const x = readNumber(value.x);
    const y = readNumber(value.y);
    if (x == null || y == null) return null;
    return { x, y };
  }
  return null;
}

function parseNormalizedPoints(value: unknown): NormalizedPoint[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((point) => parseNormalizedPoint(point))
    .filter((point): point is NormalizedPoint => point != null);
}

function bboxFromRect(rect: NormalizedRect): NormalizedRect {
  return { ...rect };
}

function bboxFromPoints(points: NormalizedPoint[]): NormalizedRect | null {
  if (points.length === 0) return null;
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return {
    x: minX,
    y: minY,
    width: Math.max(0, maxX - minX),
    height: Math.max(0, maxY - minY),
  };
}

function rectFromGeometry(geometry: Record<string, unknown>): NormalizedRect | null {
  const x = readNumber(geometry.x);
  const y = readNumber(geometry.y);
  const width = readNumber(geometry.width);
  const height = readNumber(geometry.height);
  if (x == null || y == null || width == null || height == null) {
    return null;
  }
  return { x, y, width, height };
}

function bboxFromGeometry(geometry: Record<string, unknown>): NormalizedRect | null {
  const rect = rectFromGeometry(geometry);
  if (rect) {
    return bboxFromRect(rect);
  }

  const nestedBbox = geometry.bbox;
  if (isRecord(nestedBbox)) {
    const x = readNumber(nestedBbox.x);
    const y = readNumber(nestedBbox.y);
    const width = readNumber(nestedBbox.width);
    const height = readNumber(nestedBbox.height);
    if (x != null && y != null && width != null && height != null) {
      return { x, y, width, height };
    }
  }

  const points = parseNormalizedPoints(geometry.points);
  return bboxFromPoints(points);
}

/** Convert persisted overlay geometry into a viewer-compatible diff region shape. */
export function overlayGeometryToDiffRegion(
  geometry: Record<string, unknown>
): DrawingDiffRegion | null {
  const page = readNumber(geometry.page);
  const label =
    typeof geometry.label === "string" && geometry.label.trim()
      ? geometry.label.trim()
      : null;

  const rect = rectFromGeometry(geometry);
  if (rect) {
    return {
      shapeType: "rect",
      rect,
      page,
      note: label,
    };
  }

  const nestedBbox = geometry.bbox;
  if (isRecord(nestedBbox)) {
    return {
      bbox: {
        x: readNumber(nestedBbox.x) ?? 0,
        y: readNumber(nestedBbox.y) ?? 0,
        width: readNumber(nestedBbox.width) ?? 0,
        height: readNumber(nestedBbox.height) ?? 0,
      },
      page,
      note: label,
    };
  }

  const points = parseNormalizedPoints(geometry.points);
  if (points.length >= 3) {
    return {
      shapeType: "polygon",
      points,
      page,
      note: label,
    };
  }

  if (points.length === 2) {
    const bbox = bboxFromPoints(points);
    if (!bbox) return null;
    return {
      shapeType: "rect",
      rect: bbox,
      page,
      note: label,
    };
  }

  return null;
}

/** Map GET /overlays rows into normalized overlay regions for the viewer stack. */
export function toOverlayRegions(overlays: DrawingOverlay[]): OverlayRegion[] {
  const regions: OverlayRegion[] = [];

  for (const overlay of overlays) {
    if (!isRecord(overlay.geometry)) continue;

    const shape = overlayGeometryToDiffRegion(overlay.geometry);
    if (!shape) continue;

    const bbox = bboxFromGeometry(overlay.geometry);
    if (!bbox) continue;

    const meta = isRecord(overlay.meta) ? overlay.meta : null;
    const inspectionRunId = readInspectionRunId(overlay);
    const diffId = readDiffId(overlay);
    const kind: OverlayRegionKind = inspectionRunId != null ? "inspection" : "diff";
    const reviewBadge = overlayStatusToReviewBadge(overlay.status);

    regions.push({
      id: overlay.id,
      kind,
      sourceId: inspectionRunId ?? diffId,
      label: readLabel(overlay.geometry, meta),
      severity: readSeverity(overlay, meta),
      bbox,
      shape: {
        ...shape,
        id: overlay.id,
        reviewBadge,
      },
      reviewBadge,
    });
  }

  return regions;
}

export function overlayRegionTone(
  region: OverlayRegion,
  showInspectionStatuses: boolean
): OverlayInspectionTone {
  if (!showInspectionStatuses) {
    return "neutral";
  }
  const badge = region.reviewBadge ?? region.shape.reviewBadge ?? null;
  if (badge === "passed" || badge === "failed" || badge === "changed") {
    return badge;
  }
  return region.kind === "inspection" ? "changed" : "changed";
}

export function includeOverlayWhenChangesOnly(
  region: OverlayRegion,
  showChangesOnly: boolean
): boolean {
  if (!showChangesOnly) {
    return true;
  }
  const badge = region.reviewBadge ?? region.shape.reviewBadge;
  return badge == null || badge === "changed";
}

export function regionOverlayTone(
  region: DrawingDiffRegion,
  diff: DrawingDiff,
  showInspectionStatuses: boolean
): OverlayInspectionTone {
  if (!showInspectionStatuses) {
    return "neutral";
  }
  const badge = region.reviewBadge ?? diff.reviewBadge ?? null;
  if (badge === "passed" || badge === "failed" || badge === "changed") {
    return badge;
  }
  return "changed";
}

export function includeRegionWhenChangesOnly(
  region: DrawingDiffRegion,
  diff: DrawingDiff,
  showChangesOnly: boolean
): boolean {
  if (!showChangesOnly) {
    return true;
  }
  const badge = region.reviewBadge ?? diff.reviewBadge;
  return badge == null || badge === "changed";
}
