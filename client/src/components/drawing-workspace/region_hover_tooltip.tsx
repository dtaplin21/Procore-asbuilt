/**
 * Radix tooltip wrapper rendering the fields from region_tooltip.ts.
 * Controlled (open driven by the parent's hover state via
 * DrawingRegionLayer's onRegionHoverChange) rather than Radix's own
 * hover-trigger behavior, since the hover target is an SVG shape positioned
 * by percentage math, not a normal DOM child Radix can anchor a trigger to
 * directly — the parent already knows exactly when hover starts/ends and at
 * what region, so it drives this tooltip's visibility explicitly.
 */

import * as Tooltip from "@radix-ui/react-tooltip";

import { buildRegionTooltipContent } from "@/lib/drawing-regions/region_tooltip";
import type { RenderableRegion } from "@/lib/drawing-regions/region_display";

export interface RegionHoverTooltipProps {
  hoveredRegion: RenderableRegion | null;
  /** Pixel position to anchor the tooltip at — typically from mouse/client coords. */
  anchorPosition: { x: number; y: number } | null;
}

export function RegionHoverTooltip({ hoveredRegion, anchorPosition }: RegionHoverTooltipProps) {
  if (!hoveredRegion || !anchorPosition) {
    return null;
  }

  const content = buildRegionTooltipContent(hoveredRegion.entry, hoveredRegion.state);

  return (
    <Tooltip.Provider delayDuration={0}>
      <Tooltip.Root open>
        <Tooltip.Trigger asChild>
          <span
            aria-hidden
            style={{
              position: "fixed",
              left: anchorPosition.x,
              top: anchorPosition.y,
              width: 1,
              height: 1,
              pointerEvents: "none",
            }}
          />
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            data-testid="region-hover-tooltip"
            side="top"
            sideOffset={8}
            style={{
              backgroundColor: "#111827",
              color: "white",
              borderRadius: 6,
              padding: "8px 12px",
              fontSize: 13,
              lineHeight: 1.5,
              boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
              zIndex: 50,
            }}
          >
            <div data-testid="region-tooltip-location">
              <strong>Location:</strong> {content.locationLine}
            </div>
            <div data-testid="region-tooltip-inspection">
              <strong>Inspection:</strong> {content.inspectionLine}
            </div>
            {content.dateLine && (
              <div data-testid="region-tooltip-date">
                <strong>Date:</strong> {content.dateLine}
              </div>
            )}
            {content.inspectionNumberLine && (
              <div data-testid="region-tooltip-number">
                <strong>Inspection #:</strong> {content.inspectionNumberLine}
              </div>
            )}
            {content.statusLine && (
              <div data-testid="region-tooltip-status">
                <strong>Status:</strong> {content.statusLine}
              </div>
            )}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
