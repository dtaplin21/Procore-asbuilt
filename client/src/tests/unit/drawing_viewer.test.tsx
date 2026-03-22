import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import DrawingViewer from "@/components/drawing-workspace/drawing_viewer";
import type {
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
    unobserve() {}
  }

  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
});

describe("DrawingViewer", () => {
  it("renders image viewer for drawing file url", () => {
    const drawing: DrawingWorkspaceDrawing = {
      id: 10,
      projectId: 1,
      name: "Master Drawing",
      fileUrl: "/test-image.png",
      sourceFileUrl: "/api/projects/1/drawings/10/file",
      pageCount: 1,
      activePage: 1,
      processingStatus: "ready",
      source: "master",
    };

    render(<DrawingViewer drawing={drawing} selectedDiff={null} />);

    expect(screen.getByTestId("drawing-viewer-image")).toBeInTheDocument();
  });

  it("renders empty state when file url is missing", () => {
    const drawing = {
      id: 10,
      projectId: 1,
      name: "Master Drawing",
      fileUrl: "",
      sourceFileUrl: "/api/projects/1/drawings/10/file",
      pageCount: 1,
      activePage: 1,
      processingStatus: "ready",
      source: "master",
    } as DrawingWorkspaceDrawing;

    render(<DrawingViewer drawing={drawing} selectedDiff={null} />);

    expect(screen.getByText("Drawing file unavailable")).toBeInTheDocument();
  });

  it("accepts a selected diff without crashing", () => {
    const drawing: DrawingWorkspaceDrawing = {
      id: 10,
      projectId: 1,
      name: "Master Drawing",
      fileUrl: "/test-image.png",
      sourceFileUrl: "/api/projects/1/drawings/10/file",
      pageCount: 1,
      activePage: 1,
      processingStatus: "ready",
      source: "master",
    };

    const diff: DrawingDiff = {
      id: 1,
      alignmentId: 2,
      summary: "Selected diff",
      severity: "medium",
      createdAt: null,
      diffRegions: [
        {
          shapeType: "rect",
          rect: {
            x: 0.1,
            y: 0.2,
            width: 0.3,
            height: 0.15,
          },
        },
      ],
    };

    render(<DrawingViewer drawing={drawing} selectedDiff={diff} />);

    expect(screen.getByText(/Selected diff #1/)).toBeInTheDocument();
  });
});
