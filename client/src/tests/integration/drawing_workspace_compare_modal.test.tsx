/**
 * Test file 1 — parent / page integration (drawing workspace + compare modal wiring).
 *
 * Covers: modal from parent, `compareSubDrawingToMaster({ projectId, masterDrawingId, subDrawingId })`, merge hook.
 *
 * Modal-only behavior (tabs, upload, busy locks, error copy) lives in:
 * `client/src/tests/unit/compare_sub_drawing_modal.test.tsx` (test file 2).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DrawingWorkspaceBody } from "@/pages/drawing_workspace";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import { useProjectDrawings } from "@/hooks/use_project_drawings";
import { useWorkspaceSelectionQueryParams } from "@/hooks/use_workspace_selection_query_params";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

const apiMocks = vi.hoisted(() => ({
  compareSubDrawingToMaster: vi.fn(),
}));

vi.mock("@/lib/api/drawing_workspace", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/drawing_workspace")>();
  return {
    ...actual,
    compareSubDrawingToMaster: apiMocks.compareSubDrawingToMaster,
  };
});

vi.mock("@/hooks/use_drawing_workspace", () => ({
  useDrawingWorkspace: vi.fn(),
}));

vi.mock("@/hooks/use_workspace_selection_query_params", () => ({
  useWorkspaceSelectionQueryParams: vi.fn(),
}));

vi.mock("@/hooks/use_project_drawings", () => ({
  useProjectDrawings: vi.fn(),
}));

const mockUseDrawingWorkspace = vi.mocked(useDrawingWorkspace);
const mockUseWorkspaceSelectionQueryParams = vi.mocked(
  useWorkspaceSelectionQueryParams
);
const mockUseProjectDrawings = vi.mocked(useProjectDrawings);

const masterDrawing: DrawingWorkspaceDrawing = {
  id: 10,
  projectId: 1,
  name: "Master",
  fileUrl: "/f.png",
  sourceFileUrl: "/s",
  pageCount: 1,
  activePage: 1,
  processingStatus: "ready",
};

const compareResponse = {
  masterDrawing: null,
  subDrawing: { id: 201, projectId: 1, name: "Sub", fileUrl: "/x" },
  alignment: {
    id: 2,
    method: "auto",
    status: "ready",
    subDrawing: { id: 201, name: "Sub", fileUrl: "/x" },
    transform: null,
    createdAt: "2025-02-15T12:00:00Z",
  },
  diffs: [],
};

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DrawingWorkspaceBody parsedProjectId={1} parsedDrawingId={10} />
    </QueryClientProvider>
  );
}

describe("Drawing workspace — compare modal parent integration", () => {
  let beginCompareOperation: ReturnType<typeof vi.fn>;
  let mergeCompareResponse: ReturnType<typeof vi.fn>;

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
    beginCompareOperation = vi.fn(() => 1);
    mergeCompareResponse = vi.fn().mockResolvedValue({
      alignment: compareResponse.alignment,
      diffs: [],
    });

    apiMocks.compareSubDrawingToMaster.mockResolvedValue(compareResponse);

    mockUseWorkspaceSelectionQueryParams.mockReturnValue({
      alignmentIdFromUrl: null,
      diffIdFromUrl: null,
      setSelectionQueryParams: vi.fn(),
    });
    mockUseProjectDrawings.mockReturnValue({
      drawings: [
        { id: 201, projectId: 1, name: "Candidate drawing", source: "upload" },
      ],
      loading: false,
      error: null,
      reload: vi.fn().mockResolvedValue(undefined),
    });
    mockUseDrawingWorkspace.mockReturnValue({
      masterDrawing,
      alignments: [],
      selectedAlignmentId: null,
      selectedDiffId: null,
      diffsByAlignmentId: {},
      workspaceLoading: false,
      diffsLoading: false,
      workspaceError: null,
      diffsError: null,
      selectedDiffs: [],
      selectedAlignment: null,
      selectedDiff: null,
      selectAlignment: vi.fn(),
      selectDiff: vi.fn(),
      reloadWorkspace: vi.fn().mockResolvedValue(undefined),
      reloadSelectedDiffs: vi.fn().mockResolvedValue(undefined),
      beginCompareOperation,
      mergeCompareResponse,
    });
  });

  it("shows compare error and loading state from the page compare handler", async () => {
    apiMocks.compareSubDrawingToMaster.mockRejectedValue(
      new Error("Compare failed on server")
    );

    renderWorkspace();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-button"));

    expect(screen.getByTestId("compare-sub-drawing-modal")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    });

    await waitFor(() => {
      expect(screen.getByText("Compare failed on server")).toBeInTheDocument();
    });
  });

  it("shows Comparing… while compareSubDrawingToMaster is in flight", async () => {
    let resolveCompare!: (value: typeof compareResponse) => void;
    const pending = new Promise<typeof compareResponse>((resolve) => {
      resolveCompare = resolve;
    });
    apiMocks.compareSubDrawingToMaster.mockReturnValue(pending);

    renderWorkspace();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-button"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    });

    expect(screen.getByTestId("confirm-compare-sub-drawing-button")).toHaveTextContent(
      "Comparing..."
    );

    await act(async () => {
      resolveCompare(compareResponse);
    });
  });

  it("calls compareSubDrawingToMaster with route master + selected sub, then mergeCompareResponse", async () => {
    renderWorkspace();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-button"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    });

    await waitFor(() => {
      expect(apiMocks.compareSubDrawingToMaster).toHaveBeenCalledWith({
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
      });
    });

    await waitFor(() => {
      expect(mergeCompareResponse).toHaveBeenCalledWith(compareResponse, 1);
    });
  });
});
