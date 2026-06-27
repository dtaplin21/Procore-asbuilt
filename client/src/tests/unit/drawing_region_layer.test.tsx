import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DrawingRegionLayer } from "@/components/drawing-workspace/drawing_region_layer";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function entry(
  overrides: Partial<RegionInspectionSummaryEntry> & Pick<RegionInspectionSummaryEntry, "regionId" | "state">,
): RegionInspectionSummaryEntry {
  return {
    masterDrawingId: 1,
    label: "Zone",
    bbox: [0.1, 0.1, 0.3, 0.3],
    locationTags: [],
    inspectionTypeTags: [],
    ...overrides,
  };
}

function regionGroup(regionId: number) {
  return document.querySelector(`[data-region-id="${regionId}"]`);
}

describe("DrawingRegionLayer", () => {
  it("renders nothing when no regions are visible", () => {
    const { container } = render(
      <DrawingRegionLayer
        summary={[entry({ regionId: 1, state: "hidden" })]}
        showInspectableAreas={false}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it("renders bold inspected regions by default", () => {
    render(
      <DrawingRegionLayer
        summary={[entry({ regionId: 5, state: "inspected" })]}
        showInspectableAreas={false}
      />,
    );

    const shape = regionGroup(5);
    expect(shape).toHaveAttribute("data-region-state", "inspected");
    expect(shape?.querySelector("rect")?.getAttribute("x")).toBe("10");
    expect(shape?.querySelector("rect")?.getAttribute("width")).toBe("20");
  });

  it("renders faint hidden regions when admin toggle is on", () => {
    render(
      <DrawingRegionLayer
        summary={[
          entry({ regionId: 1, state: "hidden" }),
          entry({ regionId: 2, state: "inspected" }),
        ]}
        showInspectableAreas
      />,
    );

    expect(regionGroup(1)).toHaveAttribute("data-region-state", "setup_faint");
    expect(regionGroup(2)).toHaveAttribute("data-region-state", "inspected");
  });

  it("reports hover and click handlers", () => {
    const onRegionHoverChange = vi.fn();
    const onRegionClick = vi.fn();

    render(
      <DrawingRegionLayer
        summary={[entry({ regionId: 3, state: "inspected" })]}
        showInspectableAreas={false}
        onRegionHoverChange={onRegionHoverChange}
        onRegionClick={onRegionClick}
      />,
    );

    const shape = regionGroup(3);
    expect(shape).not.toBeNull();
    fireEvent.mouseEnter(shape!, { clientX: 12, clientY: 34 });
    fireEvent.mouseLeave(shape!);
    fireEvent.click(shape!);

    expect(onRegionHoverChange).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ state: "inspected" }),
      { x: 12, y: 34 },
    );
    expect(onRegionHoverChange).toHaveBeenNthCalledWith(2, null);
    expect(onRegionClick).toHaveBeenCalledWith(
      expect.objectContaining({ entry: expect.objectContaining({ regionId: 3 }) }),
    );
  });
});
