/**
 * client/src/tests/unit/drawing_region_layer.test.tsx
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DrawingRegionLayer } from "@/components/drawing-workspace/drawing_region_layer";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function makeEntry(
  overrides: Partial<RegionInspectionSummaryEntry> = {},
): RegionInspectionSummaryEntry {
  return {
    regionId: 1,
    masterDrawingId: 42,
    state: "hidden",
    label: "Roof",
    bbox: [0.1, 0.1, 0.2, 0.2],
    locationTags: ["Roof"],
    inspectionTypeTags: ["Final"],
    latestOverlayId: null,
    latestInspectionRunId: null,
    inspectionStatusDisplay: null,
    inspectionDate: null,
    procoreInspectionId: null,
    ...overrides,
  };
}

describe("DrawingRegionLayer", () => {
  it("renders nothing when there are no renderable regions", () => {
    const { container } = render(
      <DrawingRegionLayer
        summary={[makeEntry({ state: "hidden" })]}
        showInspectableAreas={false}
      />,
    );
    expect(container.querySelector('[data-testid="drawing-region-layer"]')).not.toBeInTheDocument();
  });

  it("renders one shape per inspected region", () => {
    const summary = [
      makeEntry({ regionId: 1, state: "inspected" }),
      makeEntry({ regionId: 2, state: "inspected" }),
    ];
    render(<DrawingRegionLayer summary={summary} showInspectableAreas={false} />);
    expect(screen.getAllByTestId("region-shape")).toHaveLength(2);
  });

  it("does not render hidden regions when the admin toggle is off", () => {
    const summary = [makeEntry({ regionId: 1, state: "hidden" })];
    render(<DrawingRegionLayer summary={summary} showInspectableAreas={false} />);
    expect(screen.queryByTestId("region-shape")).not.toBeInTheDocument();
  });

  it("renders faint outlines for hidden regions when the admin toggle is on", () => {
    const summary = [makeEntry({ regionId: 1, state: "hidden" })];
    render(<DrawingRegionLayer summary={summary} showInspectableAreas={true} />);
    const shape = screen.getByTestId("region-shape");
    expect(shape).toHaveAttribute("data-region-state", "setup_faint");
  });

  it("calls onRegionHoverChange with the region on hover, and null on leave", () => {
    const onRegionHoverChange = vi.fn();
    const summary = [makeEntry({ regionId: 1, state: "inspected" })];
    render(
      <DrawingRegionLayer
        summary={summary}
        showInspectableAreas={false}
        onRegionHoverChange={onRegionHoverChange}
      />,
    );

    const shape = screen.getByTestId("region-shape");
    fireEvent.mouseEnter(shape, { clientX: 50, clientY: 60 });
    expect(onRegionHoverChange).toHaveBeenCalledWith(
      expect.objectContaining({ entry: expect.objectContaining({ regionId: 1 }) }),
      expect.objectContaining({ x: 50, y: 60 }),
    );

    fireEvent.mouseLeave(shape);
    expect(onRegionHoverChange).toHaveBeenLastCalledWith(null);
  });

  it("calls onRegionClick when a region shape is clicked", () => {
    const onRegionClick = vi.fn();
    const summary = [makeEntry({ regionId: 1, state: "inspected" })];
    render(
      <DrawingRegionLayer
        summary={summary}
        showInspectableAreas={false}
        onRegionClick={onRegionClick}
      />,
    );
    fireEvent.click(screen.getByTestId("region-shape"));
    expect(onRegionClick).toHaveBeenCalledTimes(1);
  });
});
