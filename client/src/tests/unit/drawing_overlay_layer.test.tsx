import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import type { DrawingDiff } from "@/types/drawing_workspace";

describe("DrawingOverlayLayer", () => {
  it("renders rectangle overlays for selected diff regions", () => {
    const diff: DrawingDiff = {
      id: 1,
      alignmentId: 2,
      summary: "Test diff",
      severity: "medium",
      createdAt: null,
      diffRegions: [
        {
          shapeType: "rect",
          rect: {
            x: 0.1,
            y: 0.2,
            width: 0.25,
            height: 0.15,
          },
        },
      ],
    };

    render(
      <DrawingOverlayLayer
        diff={diff}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(screen.getByTestId("drawing-overlay-layer")).toBeInTheDocument();
    expect(screen.getByTestId("diff-overlay-rect-0")).toBeInTheDocument();
  });

  it("renders polygon overlays", () => {
    const diff: DrawingDiff = {
      id: 1,
      alignmentId: 2,
      summary: "Test polygon diff",
      severity: "medium",
      createdAt: null,
      diffRegions: [
        {
          shapeType: "polygon",
          points: [
            { x: 0.1, y: 0.2 },
            { x: 0.2, y: 0.2 },
            { x: 0.15, y: 0.35 },
          ],
        },
      ],
    };

    render(
      <DrawingOverlayLayer
        diff={diff}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(screen.getByTestId("diff-overlay-polygon-0")).toBeInTheDocument();
  });

  it("renders nothing when diff is null", () => {
    const { container } = render(
      <DrawingOverlayLayer
        diff={null}
        viewerSize={{ width: 1000, height: 800 }}
      />
    );

    expect(container.firstChild).toBeNull();
  });
});
