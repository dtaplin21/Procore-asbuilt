/**
 * client/src/tests/unit/drawing_viewer.test.tsx
 *
 * Per the region-visibility spec PR4: "Suppress duplicate overlay
 * rectangles" — these tests specifically verify that behavior, plus
 * basic region-layer wiring into DrawingViewer.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import DrawingViewer from "@/components/drawings/DrawingViewer";
import type { DrawingOverlay } from "@shared/schema";
import type { DrawingMarkup } from "@/types/drawing_markup";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";
import { getQueryFn } from "@/lib/queryClient";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

const markupApi = vi.hoisted(() => ({
  markups: [] as DrawingMarkup[],
  summary: [] as { inspection_type: string | null; status: string | null; count: number }[],
  create: vi.fn(),
}));

vi.mock("@/hooks/useDrawingMarkups", () => ({
  useDrawingMarkups: () => ({
    markups: markupApi.markups,
    summary: markupApi.summary,
    loading: false,
    error: null,
    reload: vi.fn(),
    create: markupApi.create,
    update: vi.fn(),
    remove: vi.fn(),
  }),
}));

vi.mock("@/hooks/use_resize_observer", () => ({
  useResizeObserver: () => ({ width: 1000, height: 800 }),
}));

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
    unobserve() {}
  }

  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
});

beforeEach(() => {
  markupApi.markups = [];
  markupApi.summary = [];
  markupApi.create.mockReset();
  markupApi.create.mockResolvedValue(null);
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

function renderReadyViewer(ui: ReactElement) {
  const view = renderViewer(ui);
  fireEvent.load(screen.getByTestId("drawing-viewer-image"));
  return view;
}

function makeOverlay(overrides: Partial<DrawingOverlay> = {}): DrawingOverlay {
  return {
    id: 1,
    master_drawing_id: 10,
    inspection_run_id: 5,
    diff_id: null,
    region_id: null,
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
    ...overrides,
  };
}

function makeRegionEntry(
  overrides: Partial<RegionInspectionSummaryEntry> = {},
): RegionInspectionSummaryEntry {
  return {
    regionId: 7,
    masterDrawingId: 10,
    state: "inspected",
    label: "Roof",
    bbox: [0.1, 0.1, 0.2, 0.2],
    locationTags: ["Roof"],
    inspectionTypeTags: ["Final"],
    latestOverlayId: 1,
    latestInspectionRunId: 5,
    inspectionStatusDisplay: "Approved",
    inspectionDate: "2026-06-24",
    procoreInspectionId: null,
    ...overrides,
  };
}

describe("DrawingViewer — shell", () => {
  it("renders image viewer for drawing file url", () => {
    renderViewer(<DrawingViewer projectId={1} drawing={readyDrawing} />);
    expect(screen.getByTestId("drawing-viewer-image")).toBeInTheDocument();
  });

  it("renders empty state when file url is missing", () => {
    const drawing = {
      ...readyDrawing,
      fileUrl: "",
    } as DrawingWorkspaceDrawing;

    renderViewer(<DrawingViewer projectId={1} drawing={drawing} />);
    expect(screen.getByText("Drawing file unavailable")).toBeInTheDocument();
  });

  it("shows overlay region count in header", async () => {
    renderViewer(<DrawingViewer projectId={1} drawing={readyDrawing} />);
    expect(await screen.findByText("0 overlay region(s)")).toBeInTheDocument();
  });

  it("uses parent-supplied overlays without refetching", async () => {
    renderViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        inspectionRunId={5}
        overlays={[makeOverlay()]}
        overlaysLoading={false}
      />,
    );
    expect(await screen.findByText("1 overlay region(s)")).toBeInTheDocument();
  });
});

describe("DrawingViewer — PR4 region visibility", () => {
  it("renders overlay shapes as before when no region summary is provided (default [])", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[makeOverlay()]}
        overlaysLoading={false}
      />,
    );
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("renders the region layer when a summary is provided", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry()]}
      />,
    );
    expect(screen.getByTestId("drawing-region-layer")).toBeInTheDocument();
  });

  it("suppresses the overlay pin for an overlay whose linked region is inspected", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[makeOverlay({ id: 1, region_id: 7 })]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry({ regionId: 7, state: "inspected" })]}
      />,
    );

    expect(screen.getByTestId("region-shape")).toBeInTheDocument();
    expect(screen.queryByTestId("overlay-rect-0")).not.toBeInTheDocument();
  });

  it("does NOT suppress an overlay pin whose region is not in the inspected summary", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[makeOverlay({ region_id: 7 })]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry({ regionId: 7, state: "hidden" })]}
      />,
    );
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("does NOT suppress an overlay pin with no region_id at all", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[makeOverlay({ region_id: null })]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry({ regionId: 7, state: "inspected" })]}
      />,
    );
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("only suppresses the overlay matching the inspected region, not all overlays", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[
          makeOverlay({
            id: 1,
            region_id: 7,
            geometry: { type: "rect", x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
          }),
          makeOverlay({
            id: 2,
            region_id: null,
            geometry: { type: "rect", x: 0.5, y: 0.5, width: 0.1, height: 0.1 },
          }),
        ]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry({ regionId: 7, state: "inspected" })]}
      />,
    );

    expect(screen.getAllByTestId(/overlay-rect-/)).toHaveLength(1);
    expect(screen.getByTestId("overlay-group-0")).toHaveAttribute("data-overlay-id", "2");
  });

  it("passes through region click callbacks", () => {
    const onRegionClick = vi.fn();

    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry()]}
        onRegionClick={onRegionClick}
      />,
    );

    fireEvent.click(screen.getByTestId("region-shape"));
    expect(onRegionClick).toHaveBeenCalledTimes(1);
  });

  it("shows the hover tooltip with the region's fields when hovering a region shape", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[]}
        overlaysLoading={false}
        regionSummary={[
          makeRegionEntry({
            regionId: 44,
            locationTags: ["Storm Drain #44"],
            inspectionTypeTags: ["Underground Storm Drain"],
            inspectionStatusDisplay: "Approved As Noted",
            latestInspectionRunId: 128,
          }),
        ]}
      />,
    );

    expect(screen.queryByTestId("region-hover-tooltip")).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId("region-shape"), { clientX: 100, clientY: 100 });

    expect(screen.getAllByTestId("region-hover-tooltip").length).toBeGreaterThan(0);
    expect(
      screen.getAllByTestId("region-tooltip-location").some((el) => el.textContent?.includes("Storm Drain #44")),
    ).toBe(true);
    expect(
      screen
        .getAllByTestId("region-tooltip-inspection")
        .some((el) => el.textContent?.includes("Underground Storm Drain")),
    ).toBe(true);
    expect(
      screen.getAllByTestId("region-tooltip-status").some((el) => el.textContent?.includes("Approved As Noted")),
    ).toBe(true);
    expect(
      screen.getAllByTestId("region-tooltip-number").some((el) => el.textContent?.includes("Run 128")),
    ).toBe(true);
  });

  it("hides the hover tooltip when the mouse leaves the region shape", () => {
    renderReadyViewer(
      <DrawingViewer
        projectId={1}
        drawing={readyDrawing}
        overlays={[]}
        overlaysLoading={false}
        regionSummary={[makeRegionEntry()]}
      />,
    );

    fireEvent.mouseEnter(screen.getByTestId("region-shape"), { clientX: 100, clientY: 100 });
    expect(screen.getAllByTestId("region-hover-tooltip").length).toBeGreaterThan(0);

    fireEvent.mouseLeave(screen.getByTestId("region-shape"));
    expect(screen.queryByTestId("region-hover-tooltip")).not.toBeInTheDocument();
  });
});

describe("DrawingViewer — markups", () => {
  const pointer = (el: Element, type: string, x: number, y: number) => {
    act(() => {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));
    });
  };

  it("keeps the markup layer on the page image inside the zoom box", () => {
    renderReadyViewer(<DrawingViewer projectId={1} drawing={readyDrawing} />);
    const stage = screen.getByTestId("drawing-viewer-stage");
    const page = screen.getByTestId("drawing-viewer-page");
    const image = screen.getByTestId("drawing-viewer-image");
    const layer = screen.getByTestId("markup-layer");

    expect(page.contains(image)).toBe(true);
    expect(page.contains(layer)).toBe(true);
    expect(stage.contains(page)).toBe(true);
    expect(layer.parentElement?.parentElement).toBe(page);
    expect(screen.getByTestId("pan-zoom-content").contains(layer)).toBe(true);
    expect(screen.getByRole("toolbar", { name: "Markup tools" })).toBeInTheDocument();
  });

  it("maps an edge-to-edge line to the page edges at two image sizes", () => {
    renderReadyViewer(<DrawingViewer projectId={1} drawing={readyDrawing} />);
    fireEvent.click(screen.getByRole("button", { name: "polyline" }));
    const layer = screen.getByTestId("markup-layer");

    for (const size of [
      { width: 1000, height: 500 },
      { width: 400, height: 200 },
    ]) {
      layer.getBoundingClientRect = () =>
        ({
          left: 10,
          top: 20,
          width: size.width,
          height: size.height,
          right: 10 + size.width,
          bottom: 20 + size.height,
          x: 10,
          y: 20,
          toJSON() {},
        }) as DOMRect;
      pointer(layer, "pointerdown", 10, 20);
      pointer(layer, "pointerdown", 10 + size.width, 20 + size.height);
      fireEvent.keyDown(window, { key: "Enter" });
    }

    expect(markupApi.create).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ kind: "polyline", points: [[0, 0], [1, 1]] }),
    );
    expect(markupApi.create).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ kind: "polyline", points: [[0, 0], [1, 1]] }),
    );
  });

  it("draws a saved markup back on the page", () => {
    markupApi.summary = [{ inspection_type: "Final", status: "Open", count: 1 }];
    markupApi.markups = [
      {
        id: 3,
        drawingId: 10,
        page: 1,
        kind: "polyline",
        points: [[0, 0], [1, 1]],
        label: null,
        inspectionType: "Final",
        status: "Open",
        color: null,
        createdBy: "Dom",
        createdAt: "",
        updatedAt: "",
      },
    ];
    renderReadyViewer(<DrawingViewer projectId={1} drawing={readyDrawing} />);
    const page = screen.getByTestId("drawing-viewer-page");
    const line = page.querySelector("polyline");
    expect(line?.getAttribute("points")).toBe("0,0 1,1");
  });
});
