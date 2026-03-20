import type { DrawingDiffRegion, NormalizedPoint, NormalizedRect } from "@/types/drawing_workspace";

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
