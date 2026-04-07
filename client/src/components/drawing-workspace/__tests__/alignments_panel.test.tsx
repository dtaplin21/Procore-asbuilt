import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DrawingAlignmentOverlayResponse } from "@/types/drawing_workspace";

const mutateAsyncMock = vi.fn();

vi.mock("@/hooks/use-drawing-diffs", () => ({
  useRunDrawingDiff: () => ({
    mutateAsync: mutateAsyncMock,
  }),
}));

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";

function makeOverlayAlignment(
  overrides: Partial<DrawingAlignmentOverlayResponse> = {}
): DrawingAlignmentOverlayResponse {
  return {
    id: 11,
    method: "manual",
    status: "complete",
    subDrawing: { id: 200, name: "Sub drawing" },
    transform: null,
    errorMessage: null,
    ...overrides,
  };
}

describe("AlignmentsPanel", () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
  });

  it("re-runs comparison for the selected alignment row", async () => {
    mutateAsyncMock.mockResolvedValue([]);

    render(
      <AlignmentsPanel
        projectId={42}
        masterDrawingId={100}
        alignments={[
          makeOverlayAlignment({ id: 11 }),
          makeOverlayAlignment({
            id: 12,
            method: "vision",
            status: "complete",
            subDrawing: { id: 201, name: "Other sub" },
          }),
        ]}
        selectedAlignmentId={11}
        loading={false}
        onSelectAlignment={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("alignment-rerun-11"));

    await waitFor(() => {
      expect(mutateAsyncMock).toHaveBeenCalledWith({ alignmentId: 11 });
    });
  });

  it("does not trigger row selection when rerun button is clicked", async () => {
    const onSelectAlignment = vi.fn();

    mutateAsyncMock.mockResolvedValue([]);

    render(
      <AlignmentsPanel
        projectId={42}
        masterDrawingId={100}
        alignments={[makeOverlayAlignment({ id: 11 })]}
        selectedAlignmentId={null}
        loading={false}
        onSelectAlignment={onSelectAlignment}
      />
    );

    fireEvent.click(screen.getByTestId("alignment-rerun-11"));

    await waitFor(() => {
      expect(mutateAsyncMock).toHaveBeenCalled();
    });

    expect(onSelectAlignment).not.toHaveBeenCalled();
  });

  it("shows an error if rerun fails", async () => {
    mutateAsyncMock.mockRejectedValue(new Error("Diff rerun failed"));

    render(
      <AlignmentsPanel
        projectId={42}
        masterDrawingId={100}
        alignments={[makeOverlayAlignment({ id: 11 })]}
        selectedAlignmentId={null}
        loading={false}
        onSelectAlignment={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("alignment-rerun-11"));

    expect(await screen.findByText(/diff rerun failed/i)).toBeInTheDocument();
  });
});
