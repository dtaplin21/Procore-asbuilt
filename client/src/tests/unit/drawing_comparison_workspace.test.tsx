/**
 * client/src/tests/unit/drawing_comparison_workspace.test.tsx
 */

import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";

import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";
import type { DrawingOverlay } from "@shared/schema";

vi.mock("@/components/drawings/DrawingViewer", () => ({
  default: ({
    overlays,
    onOverlayClick,
  }: {
    overlays?: DrawingOverlay[];
    onOverlayClick?: (overlay: DrawingOverlay) => void;
  }) => {
    const renderable = (overlays ?? []).filter((overlay) => {
      const geometry = overlay.geometry;
      if (geometry == null || typeof geometry !== "object") return false;
      const rect = geometry as { width?: unknown; height?: unknown };
      return typeof rect.width === "number" && typeof rect.height === "number";
    });

    return (
      <div data-testid="drawing-viewer-mock" data-overlay-count={renderable.length}>
        {renderable.map((overlay) => (
          <button
            key={overlay.id}
            type="button"
            data-testid="drawing-overlay-pin"
            data-overlay-id={String(overlay.id)}
            onClick={() => onOverlayClick?.(overlay)}
          />
        ))}
      </div>
    );
  },
}));

const readyDrawing: DrawingWorkspaceDrawing = {
  id: 10,
  projectId: 1,
  name: "Master Drawing",
  fileUrl: "/api/projects/1/drawings/10/pages/1/image",
  sourceFileUrl: "/api/projects/1/drawings/10/pages/1/image",
  pageCount: 1,
  activePage: 1,
  processingStatus: "ready",
  source: "master",
};

function makeOverlay(overrides: Partial<DrawingOverlay> = {}): DrawingOverlay {
  return {
    id: 1,
    master_drawing_id: 10,
    inspection_run_id: 5,
    diff_id: null,
    region_id: null,
    geometry: { type: "rect", x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
    status: "fail",
    created_at: "2026-06-24T12:00:00Z",
    meta: null,
    ...overrides,
  };
}

function renderWorkspace(
  props: Partial<ComponentProps<typeof DrawingComparisonWorkspace>> = {},
) {
  return render(
    <DrawingComparisonWorkspace
      projectId={1}
      masterDrawing={readyDrawing}
      overlays={[]}
      {...props}
    />,
  );
}

describe("DrawingComparisonWorkspace", () => {
  it("renders one overlay pin per overlay with a bbox", () => {
    const overlays = [
      makeOverlay({ id: 1 }),
      makeOverlay({
        id: 2,
        geometry: { type: "rect", x: 0.5, y: 0.5, width: 0.1, height: 0.1 },
      }),
    ];
    renderWorkspace({ overlays });

    expect(screen.getAllByTestId("drawing-overlay-pin")).toHaveLength(2);
  });

  it("does not render a pin for an overlay with no bbox", () => {
    renderWorkspace({
      overlays: [makeOverlay({ id: 1, geometry: null as unknown as DrawingOverlay["geometry"] })],
    });

    expect(screen.queryByTestId("drawing-overlay-pin")).not.toBeInTheDocument();
  });

  it("calls onOverlayClick with the clicked overlay", () => {
    const overlay = makeOverlay({ id: 1 });
    const onOverlayClick = vi.fn();
    renderWorkspace({ overlays: [overlay], onOverlayClick });

    fireEvent.click(screen.getByTestId("drawing-overlay-pin"));

    expect(onOverlayClick).toHaveBeenCalledWith(overlay);
  });

  it("hides overlays of a severity when its legend checkbox is unchecked", () => {
    const overlays = [
      makeOverlay({ id: 1, status: "fail" }),
      makeOverlay({
        id: 2,
        status: "pass",
        geometry: { type: "rect", x: 0.5, y: 0.5, width: 0.1, height: 0.1 },
      }),
    ];
    renderWorkspace({ overlays });

    expect(screen.getAllByTestId("drawing-overlay-pin")).toHaveLength(2);

    fireEvent.click(screen.getByLabelText(/Info/i));

    const remainingPins = screen.getAllByTestId("drawing-overlay-pin");
    expect(remainingPins).toHaveLength(1);
    expect(remainingPins[0]).toHaveAttribute("data-overlay-id", "1");
  });

  it("shows the selected run id when provided", () => {
    renderWorkspace({ overlays: [], selectedInspectionRunId: 42 });

    expect(screen.getByText("Run: 42")).toBeInTheDocument();
  });

  it("renders severity legend when overlays are parent-controlled", () => {
    renderWorkspace({
      overlays: [
        makeOverlay({ id: 1, status: "fail" }),
        makeOverlay({ id: 2, status: "pass" }),
        makeOverlay({ id: 3, status: "pass" }),
      ],
      selectedInspectionRunId: 5,
    });

    expect(screen.getByTestId("drawing-comparison-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("overlay-legend")).toBeInTheDocument();
    expect(screen.getByText(/High severity \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Info \(2\)/)).toBeInTheDocument();
  });

  it("omits severity legend when DrawingViewer owns overlay fetch", () => {
    render(
      <DrawingComparisonWorkspace projectId={1} masterDrawing={readyDrawing} />,
    );

    expect(screen.queryByTestId("overlay-legend")).not.toBeInTheDocument();
    expect(screen.getByTestId("drawing-viewer-mock")).toHaveAttribute(
      "data-overlay-count",
      "0",
    );
  });
});
