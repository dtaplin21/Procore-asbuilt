import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import type { OverlayRegion } from "@/lib/drawing-overlays/overlay-types";

function rectRegion(id: number): OverlayRegion {
  return {
    id,
    kind: "diff",
    sourceId: 2,
    label: null,
    severity: "medium",
    bbox: { x: 0.1, y: 0.2, width: 0.25, height: 0.15 },
    shape: {
      shapeType: "rect",
      rect: {
        x: 0.1,
        y: 0.2,
        width: 0.25,
        height: 0.15,
      },
    },
  };
}

describe("DrawingOverlayLayer", () => {
  it("renders rectangle overlays for overlay regions", () => {
    render(
      <DrawingOverlayLayer
        regions={[rectRegion(1)]}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(screen.getByTestId("drawing-overlay-layer")).toBeInTheDocument();
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("renders polygon overlays", () => {
    const regions: OverlayRegion[] = [
      {
        id: 1,
        kind: "inspection",
        sourceId: 5,
        label: "Zone",
        severity: "low",
        bbox: { x: 0.1, y: 0.1, width: 0.1, height: 0.15 },
        shape: {
          shapeType: "polygon",
          points: [
            { x: 0.1, y: 0.2 },
            { x: 0.2, y: 0.2 },
            { x: 0.15, y: 0.35 },
          ],
        },
        reviewBadge: "passed",
      },
    ];

    render(
      <DrawingOverlayLayer
        regions={regions}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(screen.getByTestId("overlay-polygon-0")).toBeInTheDocument();
  });

  it("renders nothing when regions is empty", () => {
    const { container } = render(
      <DrawingOverlayLayer
        regions={[]}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(container.firstChild).toBeNull();
  });
});
