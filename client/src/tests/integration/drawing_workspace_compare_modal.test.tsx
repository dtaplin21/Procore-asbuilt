/**
 * Test file 1 — parent / page integration (drawing workspace + compare modal wiring).
 *
 * Covers: modal rendered from parent, parent selection state, compare callback → runCompare.
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
  let runCompare: ReturnType<typeof vi.fn>;

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
    runCompare = vi.fn().mockResolvedValue({
      alignment: {
        id: 2,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        createdAt: "2025-02-15T12:00:00Z",
        subDrawing: { id: 201, name: "Sub" },
      },
      diffs: [],
    });

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
      compareLoading: false,
      workspaceError: null,
      diffsError: null,
      compareError: null,
      selectedDiffs: [],
      selectedAlignment: null,
      selectedDiff: null,
      selectAlignment: vi.fn(),
      selectDiff: vi.fn(),
      reloadWorkspace: vi.fn().mockResolvedValue(undefined),
      reloadSelectedDiffs: vi.fn().mockResolvedValue(undefined),
      runCompare,
    });
  });

  it("renders CompareSubDrawingModal from the page and passes compareLoading and compareError from the workspace hook", () => {
    mockUseDrawingWorkspace.mockReturnValue({
      masterDrawing,
      alignments: [],
      selectedAlignmentId: null,
      selectedDiffId: null,
      diffsByAlignmentId: {},
      workspaceLoading: false,
      diffsLoading: false,
      compareLoading: true,
      workspaceError: null,
      diffsError: null,
      compareError: "Compare failed on server",
      selectedDiffs: [],
      selectedAlignment: null,
      selectedDiff: null,
      selectAlignment: vi.fn(),
      selectDiff: vi.fn(),
      reloadWorkspace: vi.fn().mockResolvedValue(undefined),
      reloadSelectedDiffs: vi.fn().mockResolvedValue(undefined),
      runCompare,
    });

    renderWorkspace();

    expect(screen.queryByTestId("compare-sub-drawing-modal")).toBeNull();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-button"));

    expect(screen.getByTestId("compare-sub-drawing-modal")).toBeInTheDocument();
    expect(screen.getByText("Compare failed on server")).toBeInTheDocument();

    const compareBtn = screen.getByTestId("confirm-compare-sub-drawing-button");
    expect(compareBtn).toHaveTextContent("Comparing...");
  });

  it("wires compare confirm to runCompare with the selected sub drawing id", async () => {
    renderWorkspace();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-button"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    });

    await waitFor(() => {
      expect(runCompare).toHaveBeenCalledWith(201);
    });
  });
});
