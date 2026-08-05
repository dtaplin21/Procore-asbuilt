import type { DrawingRegion } from "@/lib/drawing-regions/types";

type RegionGeometry = DrawingRegion["geometry"] & {
  meta?: { source?: string; zone?: string };
};

export function isAutoIndexRegion(region: DrawingRegion): boolean {
  const geometry = region.geometry as RegionGeometry;
  return geometry.meta?.source === "auto_index";
}

export function regionSourceLabel(region: DrawingRegion): string | null {
  return isAutoIndexRegion(region) ? "Auto" : null;
}
