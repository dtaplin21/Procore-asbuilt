/**
 * Maps a RegionInspectionSummaryEntry + the admin "show inspectable areas"
 * toggle into RegionViewerState and visual style props for rendering — the
 * logic backing the visual-model spec's table:
 *
 *   Off (default): only bold inspected regions
 *   On:            faint dashed outlines for all backend regions;
 *                  inspected ones stay bold ON TOP
 *
 * Bold styling is explicitly status-agnostic (spec §3, §9: "Bold ignores
 * status") — there is exactly ONE bold style, used for every inspection
 * status. This module has no branch on status anywhere in its styling logic;
 * that's intentional, not an oversight.
 */

import type {
  RegionInspectionSummaryEntry,
  RegionViewerState,
} from "@/lib/drawing-regions/types";

export interface RegionDisplayStyle {
  state: RegionViewerState;
  stroke: string;
  strokeWidth: number;
  strokeDasharray: string | undefined;
  fill: string;
  fillOpacity: number;
}

const BOLD_STYLE: Omit<RegionDisplayStyle, "state"> = {
  stroke: "hsl(19 100% 50%)",
  strokeWidth: 3.5,
  strokeDasharray: undefined,
  fill: "hsl(19 100% 50%)",
  fillOpacity: 0.08,
};

const FAINT_STYLE: Omit<RegionDisplayStyle, "state"> = {
  stroke: "#94A3B8",
  strokeWidth: 1,
  strokeDasharray: "4,3",
  fill: "transparent",
  fillOpacity: 0,
};

export function resolveRegionViewerState(
  entry: RegionInspectionSummaryEntry,
  showInspectableAreas: boolean,
): RegionViewerState {
  if (entry.state === "inspected") {
    return "inspected";
  }
  return showInspectableAreas ? "setup_faint" : "hidden";
}

export function styleForViewerState(state: RegionViewerState): RegionDisplayStyle | null {
  if (state === "hidden") {
    return null;
  }
  if (state === "inspected") {
    return { state, ...BOLD_STYLE };
  }
  return { state, ...FAINT_STYLE };
}

export interface RenderableRegion {
  entry: RegionInspectionSummaryEntry;
  state: RegionViewerState;
  style: RegionDisplayStyle;
}

export function resolveRenderableRegions(
  entries: RegionInspectionSummaryEntry[],
  showInspectableAreas: boolean,
): RenderableRegion[] {
  const renderable: RenderableRegion[] = [];
  for (const entry of entries) {
    const state = resolveRegionViewerState(entry, showInspectableAreas);
    const style = styleForViewerState(state);
    if (style !== null) {
      renderable.push({ entry, state, style });
    }
  }
  // Inspected (bold) regions sort LAST so they paint on top of any faint
  // setup outlines occupying the same area — spec §3: "inspected ones stay
  // bold on top".
  renderable.sort((a, b) => {
    if (a.state === b.state) return 0;
    return a.state === "inspected" ? 1 : -1;
  });
  return renderable;
}
