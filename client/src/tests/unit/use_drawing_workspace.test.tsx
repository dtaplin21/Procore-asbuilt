import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

const mocks = vi.hoisted(() => ({
  fetchMasterDrawing: vi.fn(),
}));

vi.mock("@/lib/api/drawing_workspace", () => ({
  fetchMasterDrawing: mocks.fetchMasterDrawing,
}));

const fetchMasterDrawing = mocks.fetchMasterDrawing;

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

describe("useDrawingWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMasterDrawing.mockResolvedValue(baseDrawing);
  });

  it("loads the master drawing without alignments", async () => {
    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));

    expect(fetchMasterDrawing).toHaveBeenCalledWith(1, 10);
    expect(result.current.masterDrawing).toEqual(baseDrawing);
    expect(result.current.workspaceError).toBeNull();
  });

  it("surfaces load errors and clears them on reload", async () => {
    fetchMasterDrawing.mockRejectedValueOnce(new Error("Server error"));

    const { result } = renderHook(() =>
      useDrawingWorkspace({ projectId: 1, drawingId: 10 })
    );

    await waitFor(() => expect(result.current.workspaceLoading).toBe(false));
    expect(result.current.workspaceError).toBe("Server error");

    fetchMasterDrawing.mockResolvedValueOnce(baseDrawing);
    await act(async () => {
      await result.current.reloadWorkspace();
    });

    await waitFor(() => expect(result.current.masterDrawing).toEqual(baseDrawing));
    expect(result.current.workspaceError).toBeNull();
  });
});
