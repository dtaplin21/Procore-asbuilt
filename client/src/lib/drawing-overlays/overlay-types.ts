import type {
  DrawingDiffRegion,
  NormalizedPoint,
  NormalizedRect,
  ReviewBadgeTone,
} from "@/types/drawing_workspace";

export type OverlayRegionKind = "inspection" | "diff";

/** Normalized overlay row for viewer rendering (inspection or diff sourced). */
export type OverlayRegion = {
  id: number;
  kind: OverlayRegionKind;
  sourceId: number | null;
  label: string | null;
  severity: string;
  bbox: NormalizedRect;
  /** Shape payload consumed by {@link resolveOverlayRegion}. */
  shape: DrawingDiffRegion;
  reviewBadge?: ReviewBadgeTone | null;
};

export type ViewerSize = {
  width: number;
  height: number;
};

export type PixelRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PixelPoint = {
  x: number;
  y: number;
};

export type ResolvedOverlayRegion =
  | {
      kind: "rect";
      rect: NormalizedRect;
      source: DrawingDiffRegion;
    }
  | {
      kind: "polygon";
      points: NormalizedPoint[];
      source: DrawingDiffRegion;
    };
