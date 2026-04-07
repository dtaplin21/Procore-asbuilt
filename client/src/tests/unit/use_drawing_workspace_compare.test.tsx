import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { compareSubDrawingToMaster } from "@/lib/api/drawing_workspace";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import type {
  DrawingAlignment,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

const mocks = vi.hoisted(() => ({
  fetchMasterDrawing: vi.fn(),
  fetchMasterDrawingAlignments: vi.fn(),
  fetchAlignmentDiffs: vi.fn(),
  compareSubDrawingToMaster: vi.fn(),
}));

vi.mock("@/lib/api/drawing_workspace", () => ({
  fetchMasterDrawing: mocks.fetchMasterDrawing,
  fetchMasterDrawingAlignments: mocks.fetchMasterDrawingAlignments,
  fetchAlignmentDiffs: mocks.fetchAlignmentDiffs,
  compareSubDrawingToMaster: mocks.compareSubDrawingToMaster,
}));

const fetchMasterDrawing = mocks.fetchMasterDrawing;
const fetchMasterDrawingAlignments = mocks.fetchMasterDrawingAlignments;
const fetchAlignmentDiffs = mocks.fetchAlignmentDiffs;
const compareSubDrawingToMasterMock = mocks.compareSubDrawingToMaster;

const baseDrawing: DrawingWorkspaceDrawing = {
  id: 10,
  projectId: 1,
  name: "Master",
  fileUrl: "/f.png",
  sourceFileUrl: "/src",
  pageCount: 1,
  activePage: 1,
  processingStatus: "ready",
};

const alignmentA: DrawingAlignment = {
  id: 1,
  projectId: 1,
  masterDrawingId: 10,
  subDrawingId: 101,
  createdAt: "2025-02-14T12:00:00Z",
  subDrawing: { id: 101, name: "Sub A" },
};

function setupDefaultWorkspace() {
  fetchMasterDrawing.mockResolvedValue(baseDrawing);
  fetchMasterDrawingAlignments.mockResolvedValue({ alignments: [alignmentA] });
  fetchAlignmentDiffs.mockResolvedValue({
    diffs: [
      {
        id: 10,
        alignmentId: 1,
        summary: "Existing",
        createdAt: "2025-02-14T13:00:00Z",
        diffRegions: [],
      },
    ],
  });
}

async function runCompareFlow(
  result: { current: ReturnType<typeof useDrawingWorkspace> },
  subDrawingId: number
) {
  const requestId = result.current.beginCompareOperation();
  const response = await compareSubDrawingToMaster({
    projectId: 1,
    masterDrawingId: 10,
    subDrawingId,
  });
  return result.current.mergeCompareResponse(response, requestId);
}

describe("useDrawingWorkspace — compare (API + merge)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultWorkspace();
  });

  it("calls compareSubDrawingToMaster with project, master drawing, and sub drawing ids", async () => {
    compareSubDrawingToMasterMock.mockResolvedValue({
      masterDrawing: null,
      subDrawing: { id: 201, projectId: 1, name: "Sub" },
      alignment: {
        id: 2,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        createdAt: "2025-02-15T12:00:00Z",
        subDrawing: { id: 201, name: "Sub B" },
      },
      diffs: [
        {
          id: 20,
          alignmentId: 2,
          summary: "New diff",
          createdAt: "2025-02-15T12:00:00Z",
          diffRegions: [],
        },
      ],
    });

    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));

    await act(async () => {
      await runCompareFlow(result, 201);
    });

    expect(compareSubDrawingToMasterMock).toHaveBeenCalledWith({
      projectId: 1,
      masterDrawingId: 10,
      subDrawingId: 201,
    });
  });

  it("stores returned diffs under the alignment id and selects the newest diff", async () => {
    compareSubDrawingToMasterMock.mockResolvedValue({
      masterDrawing: null,
      subDrawing: { id: 201, projectId: 1, name: "Sub" },
      alignment: {
        id: 2,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        createdAt: "2025-02-15T12:00:00Z",
        subDrawing: { id: 201, name: "Sub B" },
      },
      diffs: [
        {
          id: 22,
          alignmentId: 2,
          summary: "Older",
          createdAt: "2025-02-15T10:00:00Z",
          diffRegions: [],
        },
        {
          id: 21,
          alignmentId: 2,
          summary: "Newer",
          createdAt: "2025-02-15T14:00:00Z",
          diffRegions: [],
        },
      ],
    });

    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));

    await act(async () => {
      await runCompareFlow(result, 201);
    });

    expect(result.current.diffsByAlignmentId[2]?.map((d) => d.id)).toEqual([21, 22]);
    expect(result.current.selectedAlignmentId).toBe(2);
    expect(result.current.selectedDiffId).toBe(21);
    expect(result.current.selectedDiff?.summary).toBe("Newer");
  });

  it("merges an existing alignment id in place without duplicating", async () => {
    compareSubDrawingToMasterMock.mockResolvedValue({
      masterDrawing: null,
      subDrawing: { id: 101, projectId: 1, name: "Sub A" },
      alignment: {
        ...alignmentA,
        alignmentStatus: "refreshed",
        createdAt: "2025-02-14T15:00:00Z",
      },
      diffs: [
        {
          id: 30,
          alignmentId: 1,
          summary: "Recomputed",
          createdAt: "2025-02-14T16:00:00Z",
          diffRegions: [],
        },
      ],
    });

    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));
    const countBefore = result.current.alignments.filter((a) => a.id === 1).length;
    expect(countBefore).toBe(1);

    await act(async () => {
      await runCompareFlow(result, 101);
    });

    expect(result.current.alignments.filter((a) => a.id === 1)).toHaveLength(1);
    expect(result.current.alignments.find((a) => a.id === 1)?.alignmentStatus).toBe(
      "refreshed"
    );
    expect(result.current.selectedAlignmentId).toBe(1);
  });

  it("ignores a stale merge when a newer compare operation has started", async () => {
    compareSubDrawingToMasterMock.mockResolvedValue({
      masterDrawing: null,
      subDrawing: { id: 201, projectId: 1, name: "Sub" },
      alignment: {
        id: 2,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        createdAt: "2025-02-15T12:00:00Z",
        subDrawing: { id: 201, name: "Sub B" },
      },
      diffs: [],
    });

    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));

    const staleRequestId = result.current.beginCompareOperation();
    const freshRequestId = result.current.beginCompareOperation();

    const response = await compareSubDrawingToMaster({
      projectId: 1,
      masterDrawingId: 10,
      subDrawingId: 201,
    });

    await act(async () => {
      await result.current.mergeCompareResponse(response, staleRequestId);
    });

    expect(result.current.selectedAlignmentId).toBe(1);

    await act(async () => {
      await result.current.mergeCompareResponse(response, freshRequestId);
    });

    expect(result.current.selectedAlignmentId).toBe(2);
  });
});
