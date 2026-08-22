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

  it("renders polyline overlays through resolveOverlayRegion", () => {
    const regions: OverlayRegion[] = [
      {
        id: 42,
        kind: "inspection",
        sourceId: 357,
        label: "Sanitary sewer run",
        severity: "low",
        bbox: { x: 0.41, y: 0.38, width: 0.04, height: 0.02 },
        shape: {
          shapeType: "polyline",
          scopeKind: "utility_line",
          points: [
            { x: 0.41, y: 0.38 },
            { x: 0.43, y: 0.39 },
            { x: 0.45, y: 0.4 },
          ],
        },
        reviewBadge: "changed",
      },
    ];

    render(
      <DrawingOverlayLayer
        regions={regions}
        viewerSize={{ width: 1000, height: 800 }}
        focusedOverlayId="999"
      />,
    );

    const polyline = screen.getByTestId("overlay-polyline-0");
    expect(polyline).toBeInTheDocument();
    expect(polyline).toHaveAttribute("fill", "none");
    expect(polyline).toHaveAttribute("stroke-linecap", "round");
    expect(polyline).toHaveAttribute("stroke-linejoin", "round");
    expect(polyline).toHaveAttribute("stroke-width", "3");
    expect(polyline).toHaveAttribute(
      "points",
      "410,304 430,312 450,320",
    );
    expect(screen.getByTestId("overlay-label-0")).toHaveTextContent(
      "Sanitary sewer run",
    );
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

  it("emphasizes only the focused overlay when focusedOverlayId is set", () => {
    render(
      <DrawingOverlayLayer
        regions={[rectRegion(10), rectRegion(20)]}
        viewerSize={{ width: 1000, height: 800 }}
        focusedOverlayId="20"
      />,
    );

    expect(screen.getByTestId("overlay-group-0")).toHaveAttribute(
      "data-focused",
      "false",
    );
    expect(screen.getByTestId("overlay-group-1")).toHaveAttribute(
      "data-focused",
      "true",
    );
  });
});
