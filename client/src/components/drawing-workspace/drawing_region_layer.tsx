/**
 * SVG layer: bold inspected regions (+ optional faint setup outlines when the
 * admin toggle is on). Sits stacked over the master drawing image in
 * DrawingViewer. Uses viewBox="0 0 100 100" as a fixed percentage-equivalent
 * coordinate space — region_shape.tsx's <rect> coordinates are plain numbers in
 * that same 0-100 space (NOT percentage strings).
 */

import { RegionShape } from "@/components/drawing-workspace/region_shape";
import {
  resolveRenderableRegions,
  type RenderableRegion,
} from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

export interface DrawingRegionLayerProps {
  summary: RegionInspectionSummaryEntry[];
  showInspectableAreas: boolean;
  onRegionHoverChange?: (
    region: RenderableRegion | null,
    position?: { x: number; y: number },
  ) => void;
  onRegionClick?: (region: RenderableRegion) => void;
}

export function DrawingRegionLayer({
  summary,
  showInspectableAreas,
  onRegionHoverChange,
  onRegionClick,
}: DrawingRegionLayerProps) {
  const renderable = resolveRenderableRegions(summary, showInspectableAreas);

  function handleHoverStart(region: RenderableRegion, position: { x: number; y: number }) {
    onRegionHoverChange?.(region, position);
  }

  function handleHoverEnd() {
    onRegionHoverChange?.(null);
  }

  if (renderable.length === 0) {
    return null;
  }

  return (
    <svg
      data-testid="drawing-region-layer"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <g style={{ pointerEvents: "auto" }}>
        {renderable.map((region) => (
          <RegionShape
            key={region.entry.regionId}
            region={region}
            onHoverStart={handleHoverStart}
            onHoverEnd={handleHoverEnd}
            onClick={onRegionClick}
          />
        ))}
      </g>
    </svg>
  );
}
