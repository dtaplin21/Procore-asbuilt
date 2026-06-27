import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RegionHoverTooltip } from "@/components/drawing-workspace/region_hover_tooltip";
import { styleForViewerState } from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function renderable(
  entry: RegionInspectionSummaryEntry,
  state: "inspected" | "setup_faint",
) {
  const style = styleForViewerState(state);
  if (!style) throw new Error("expected renderable style");
  return { entry, state, style };
}

describe("RegionHoverTooltip", () => {
  it("renders nothing without hover state", () => {
    const { container } = render(
      <RegionHoverTooltip hoveredRegion={null} anchorPosition={null} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders minimal lines for uninspected faint regions", () => {
    render(
      <RegionHoverTooltip
        hoveredRegion={renderable(
          {
            regionId: 1,
            masterDrawingId: 10,
            state: "hidden",
            label: "Roof",
            bbox: [0, 0, 0.1, 0.1],
            locationTags: ["Roof Area"],
            inspectionTypeTags: [],
          },
          "setup_faint",
        )}
        anchorPosition={{ x: 100, y: 200 }}
      />,
    );

    const tooltip = screen.getByTestId("region-hover-tooltip");
    expect(tooltip).toHaveTextContent("Location:");
    expect(tooltip).toHaveTextContent("Roof Area");
    expect(tooltip).toHaveTextContent("Inspection:");
    expect(tooltip).toHaveTextContent("Not yet inspected");
    expect(tooltip).not.toHaveTextContent("Status:");
  });

  it("renders full inspected tooltip fields", () => {
    render(
      <RegionHoverTooltip
        hoveredRegion={renderable(
          {
            regionId: 2,
            masterDrawingId: 10,
            state: "inspected",
            label: "Utility MR",
            bbox: [0, 0, 0.1, 0.1],
            locationTags: ["Utility MR"],
            inspectionTypeTags: ["Rough In"],
            inspectionDate: "2026-03-15",
            latestInspectionRunId: 128,
            inspectionStatusDisplay: "Approved As Noted",
          },
          "inspected",
        )}
        anchorPosition={{ x: 50, y: 60 }}
      />,
    );

    const tooltip = screen.getByTestId("region-hover-tooltip");
    expect(tooltip).toHaveTextContent("Date:");
    expect(tooltip).toHaveTextContent("Mar 15, 2026");
    expect(tooltip).toHaveTextContent("Inspection #:");
    expect(tooltip).toHaveTextContent("Run 128");
    expect(tooltip).toHaveTextContent("Status:");
    expect(tooltip).toHaveTextContent("Approved As Noted");
  });
});
