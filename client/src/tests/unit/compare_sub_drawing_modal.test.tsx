/**
 * Test file 2 — CompareSubDrawingModal unit / integration (tabs, busy locks, errors, selection, upload).
 *
 * Parent / page wiring for `DrawingWorkspaceBody` + `compareSubDrawingToMaster` is in:
 * `client/src/tests/integration/drawing_workspace_compare_modal.test.tsx` (test file 1).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import CompareSubDrawingModal from "@/components/drawing-workspace/compare_sub_drawing_modal";
import { useProjectDrawings } from "@/hooks/use_project_drawings";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

vi.mock("@/hooks/use_project_drawings", () => ({
  useProjectDrawings: vi.fn(),
}));

const mockUseProjectDrawings = vi.mocked(useProjectDrawings);

describe("CompareSubDrawingModal", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseProjectDrawings.mockReturnValue({
      drawings: [
        { id: 201, projectId: 1, name: "Candidate drawing", source: "upload" },
      ],
      loading: false,
      error: null,
      reload: vi.fn().mockResolvedValue(undefined),
    });
  });

  it("shows sub drawings, selects one, and calls onConfirmCompare with Compare", () => {
    const onConfirmCompare = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();

    renderWithProviders(
      <CompareSubDrawingModal
        open
        onOpenChange={onOpenChange}
        projectId={1}
        masterDrawingId={10}
        onConfirmCompare={onConfirmCompare}
        compareLoading={false}
        compareError={null}
      />
    );

    fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));

    expect(onConfirmCompare).toHaveBeenCalledWith(201);
  });

  it("shows Comparing... on the confirm button while compareLoading is true", () => {
    renderWithProviders(
      <CompareSubDrawingModal
        open
        onOpenChange={vi.fn()}
        projectId={1}
        masterDrawingId={10}
        onConfirmCompare={vi.fn()}
        compareLoading
        compareError={null}
      />
    );

    const btn = screen.getByTestId("confirm-compare-sub-drawing-button");
    expect(btn).toHaveTextContent("Comparing...");
    expect(btn).toBeDisabled();
  });

  it("renders compare error message for retry", () => {
    const onConfirmCompare = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <CompareSubDrawingModal
        open
        onOpenChange={vi.fn()}
        projectId={1}
        masterDrawingId={10}
        onConfirmCompare={onConfirmCompare}
        compareLoading={false}
        compareError="Compare failed on server"
      />
    );

    expect(screen.getByText("Compare failed on server")).toBeInTheDocument();
    expect(
      screen.getByText(/its render may still be processing/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    expect(onConfirmCompare).toHaveBeenCalledWith(201);
  });

  it("disables escape and backdrop close while compareLoading", () => {
    const onOpenChange = vi.fn();

    renderWithProviders(
      <CompareSubDrawingModal
        open
        onOpenChange={onOpenChange}
        projectId={1}
        masterDrawingId={10}
        onConfirmCompare={vi.fn()}
        compareLoading
        compareError={null}
      />
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onOpenChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-modal-backdrop"));
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
