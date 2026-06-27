/**
 * Renders ONE region's geometry as an SVG rect, using the style resolved by
 * region_display.ts. Exposes onHover/onLeave so the parent layer
 * (drawing_region_layer.tsx) can drive the hover tooltip (PR5) without this
 * component needing to know about tooltips itself.
 *
 * NOTE on polygon shapes: GET .../region-inspection-summary (PR1) currently
 * returns only a fractional bbox per entry, not full polygon points —
 * polygon_points lives on the region CRUD model/route (PR2's GET
 * /drawings/{id}/regions), not the summary endpoint. The bbox is sufficient
 * for PR4's "bold inspected regions" requirement (the spec's visual
 * recommendation is a rect outline regardless of true region shape). If
 * polygon-accurate bold outlines are needed later, extend
 * RegionInspectionSummaryEntry to also carry polygon_points and swap the
 * <rect> below for an SVG <polygon> using drawing-regions/geometry.ts's
 * polygonPointsToFractional(), which is already written for that extension
 * — just not wired through the summary endpoint today.
 */

import type { RenderableRegion } from "@/lib/drawing-regions/region_display";

export interface RegionShapeProps {
  region: RenderableRegion;
  onHoverStart?: (region: RenderableRegion, position: { x: number; y: number }) => void;
  onHoverEnd?: () => void;
  onClick?: (region: RenderableRegion) => void;
}

export function RegionShape({ region, onHoverStart, onHoverEnd, onClick }: RegionShapeProps) {
  const { entry, state, style } = region;
  const [x0, y0, x1, y1] = entry.bbox;

  // Parent <svg> uses viewBox="0 0 100 100" (drawing_region_layer.tsx) —
  // coordinates here are plain numbers in that 0-100 space, NOT percentage
  // strings. (Percentage strings are the right approach for DrawingViewer.tsx's
  // HTML-positioned overlay pins, which have no SVG viewBox; mixing the two
  // approaches in one SVG would silently misposition shapes, since percentage
  // attributes on SVG geometry resolve against the SVG viewport's CSS size, not
  // the viewBox.)
  const x = x0 * 100;
  const y = y0 * 100;
  const width = (x1 - x0) * 100;
  const height = (y1 - y0) * 100;

  return (
    <g
      data-testid="region-shape"
      data-region-id={entry.regionId}
      data-region-state={state}
      onMouseEnter={(e) => onHoverStart?.(region, { x: e.clientX, y: e.clientY })}
      onMouseMove={(e) => onHoverStart?.(region, { x: e.clientX, y: e.clientY })}
      onMouseLeave={() => onHoverEnd?.()}
      onClick={() => onClick?.(region)}
      style={{ cursor: onClick ? "pointer" : "default" }}
    >
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        stroke={style.stroke}
        strokeWidth={style.strokeWidth}
        strokeDasharray={style.strokeDasharray}
        fill={style.fill}
        fillOpacity={style.fillOpacity}
        vectorEffect="non-scaling-stroke"
      />
      {/* Larger invisible hit-target so hovering near the (often thin) stroke
          still registers, especially for faint setup outlines. */}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill="transparent"
        stroke="transparent"
        strokeWidth={3}
        vectorEffect="non-scaling-stroke"
      />
    </g>
  );
}
