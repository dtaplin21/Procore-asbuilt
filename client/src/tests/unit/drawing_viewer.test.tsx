import { beforeAll, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import DrawingViewer from "@/components/drawings/DrawingViewer";
import type { DrawingOverlay } from "@shared/schema";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";
import { getQueryFn } from "@/lib/queryClient";

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
    unobserve() {}
  }

  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
});

function renderViewer(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        queryFn: async (ctx) => {
          const key = ctx.queryKey[0];
          if (typeof key === "string" && key.includes("/overlays")) {
            return [];
          }
          return getQueryFn({ on401: "throw" })(ctx);
        },
      },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

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

describe("DrawingViewer", () => {
  it("renders image viewer for drawing file url", () => {
    renderViewer(
      <DrawingViewer projectId={1} drawing={readyDrawing} />
    );

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

    renderViewer(
      <DrawingViewer projectId={1} drawing={drawing} />
    );

    expect(screen.getByText("Drawing file unavailable")).toBeInTheDocument();
  });

  it("shows overlay region count in header", async () => {
    renderViewer(
      <DrawingViewer projectId={1} drawing={readyDrawing} />
    );

    expect(await screen.findByText("0 overlay region(s)")).toBeInTheDocument();
  });

  it("uses parent-supplied overlays without refetching", async () => {
    const parentOverlays = [
      {
        id: 1,
        master_drawing_id: 10,
        inspection_run_id: 5,
        diff_id: null,
        geometry: {
          type: "rect",
          x: 0.1,
          y: 0.1,
          width: 0.2,
          height: 0.2,
        },
        status: "fail",
        created_at: "2025-01-01T00:00:00Z",
        meta: null,
      },
    ] satisfies DrawingOverlay[];

    renderViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        inspectionRunId={5}
        overlays={parentOverlays}
        overlaysLoading={false}
      />
    );

    expect(await screen.findByText("1 overlay region(s)")).toBeInTheDocument();
  });
});
