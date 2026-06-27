/**
 * client/src/tests/unit/objects_page.test.tsx
 *
 * PR4/PR5 Objects page integration: overlay fetch scoping, region summary
 * rendering, inspectable-areas toggle, region editor, and ?region= URL sync.
 */

import { beforeAll, beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import ObjectsPage from "@/pages/objects";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";
import type { DrawingOverlay } from "@shared/schema";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";
import {
  createTestQueryClient,
  renderActiveProjectPage,
} from "@/tests/helpers/render_with_active_project";
import { getQueryFn } from "@/lib/queryClient";

vi.mock("@/hooks/use_resize_observer", () => ({
  useResizeObserver: () => ({ width: 1000, height: 800 }),
}));

vi.mock("@/components/ProcoreWritebackPanel", () => ({
  ProcoreWritebackPanel: () => <div data-testid="procore-writeback-mock" />,
}));

vi.mock("@/components/drawing-workspace/inspection_runs_panel", () => ({
  default: () => <div data-testid="inspection-runs-panel-mock" />,
}));

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

const PROJECT_ID = 1;
const DRAWING_ID = 1;
const RUN_ID = 15;

const SAMPLE_MASTER_DRAWING: DrawingWorkspaceDrawing = {
  id: DRAWING_ID,
  projectId: PROJECT_ID,
  name: "Sheet A",
  fileUrl: `/api/projects/${PROJECT_ID}/drawings/${DRAWING_ID}/pages/1/image`,
  sourceFileUrl: `/api/projects/${PROJECT_ID}/drawings/${DRAWING_ID}/pages/1/image`,
  pageCount: 1,
  activePage: 1,
  processingStatus: "ready",
  source: "master",
  widthPx: 1000,
  heightPx: 800,
};

const SAMPLE_OVERLAY: DrawingOverlay = {
  id: 1,
  master_drawing_id: DRAWING_ID,
  inspection_run_id: RUN_ID,
  diff_id: null,
  region_id: null,
  geometry: { type: "rect", x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
  status: "pass",
  created_at: "2026-06-24T12:00:00Z",
  meta: null,
};

const EMPTY_RUN_LIST = { items: [] as unknown[], total: 0, limit: 50, offset: 0 };

function makeSummaryEntry(
  overrides: Partial<RegionInspectionSummaryEntry> = {},
): RegionInspectionSummaryEntry {
  return {
    regionId: 1,
    masterDrawingId: DRAWING_ID,
    state: "inspected",
    label: "Roof",
    bbox: [0.3, 0.3, 0.4, 0.4],
    locationTags: ["Roof"],
    inspectionTypeTags: ["Final"],
    latestOverlayId: 1,
    latestInspectionRunId: RUN_ID,
    inspectionStatusDisplay: "Approved As Noted",
    inspectionDate: "2026-06-24",
    procoreInspectionId: null,
    ...overrides,
  };
}

type FetchMockOptions = {
  masterDrawing?: DrawingWorkspaceDrawing | "error";
  overlays?: DrawingOverlay[];
  regionSummary?: RegionInspectionSummaryEntry[];
  latestRunId?: number | null;
  onOverlayRequest?: (url: string) => void;
};

function installDefaultFetchMock(
  fetchMock: ReturnType<typeof vi.fn>,
  options: FetchMockOptions = {},
) {
  const {
    masterDrawing = SAMPLE_MASTER_DRAWING,
    overlays = [],
    regionSummary = [],
    latestRunId = RUN_ID,
    onOverlayRequest,
  } = options;

  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = requestUrl(input);

    if (url.includes("/api/projects") && url.endsWith("/api/projects")) {
      return jsonResponse({
        items: [{ id: PROJECT_ID, name: "Project One", company_id: 1 }],
      });
    }

    if (url.includes("/api/objects")) {
      return jsonResponse([]);
    }

    if (url.includes(`/api/projects/${PROJECT_ID}/drawings`) && !url.includes("/drawings/")) {
      return jsonResponse({
        drawings: [{ id: DRAWING_ID, name: "Sheet A", source: "master" }],
      });
    }

    if (url.includes(`/api/projects/${PROJECT_ID}/dashboard/summary`)) {
      return jsonResponse({
        project: {
          id: PROJECT_ID,
          name: "Project One",
          company_id: 1,
          masterDrawingId: DRAWING_ID,
        },
        masterDrawing: {
          id: DRAWING_ID,
          name: "Sheet A",
          updated_at: "2026-06-24T00:00:00Z",
        },
        company_context: { project_company_id: 1, matches_active_company: true },
        sync_health: { connected: false, sync_status: "idle" },
        kpis: {
          total_findings: 0,
          open_findings: 0,
          drawings_count: 1,
          evidence_count: 0,
          inspections_count: 0,
        },
      });
    }

    if (
      url.includes(`/api/projects/${PROJECT_ID}/drawings/${DRAWING_ID}`) &&
      !url.includes("/overlays") &&
      !url.includes("/region") &&
      !url.includes("/regions")
    ) {
      if (masterDrawing === "error") {
        return jsonResponse({ detail: "Not found" }, 404);
      }
      return jsonResponse(masterDrawing);
    }

    if (url.includes("/overlays")) {
      onOverlayRequest?.(url);
      return jsonResponse(overlays);
    }

    if (url.includes("/region-inspection-summary")) {
      return jsonResponse({ items: regionSummary });
    }

    if (url.includes(`/drawings/${DRAWING_ID}/regions`) && !url.includes("region-inspection")) {
      return jsonResponse([]);
    }

    if (url.includes("/inspections/runs") && url.includes("limit=1")) {
      if (latestRunId == null) {
        return jsonResponse({ items: [], total: 0, limit: 1, offset: 0 });
      }
      return jsonResponse({
        items: [{ id: latestRunId, master_drawing_id: DRAWING_ID, status: "complete" }],
        total: 1,
        limit: 1,
        offset: 0,
      });
    }

    if (url.includes("/inspections/runs")) {
      return jsonResponse(EMPTY_RUN_LIST);
    }

    if (url.includes("/evidence")) {
      return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
    }

    throw new Error(`Unexpected fetch: ${url}`);
  });
}

function renderObjects(initialEntry: string) {
  const queryClient = createTestQueryClient();
  queryClient.setDefaultOptions({
    queries: {
      retry: false,
      queryFn: getQueryFn({ on401: "throw" }),
    },
  });

  return renderActiveProjectPage("/objects", initialEntry, <ObjectsPage />, {
    queryClient,
  });
}

async function waitForDrawingCanvasReady() {
  const image = await screen.findByTestId("drawing-viewer-image");
  fireEvent.load(image);
}

describe("ObjectsPage", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeAll(() => {
    class ResizeObserverMock {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    installDefaultFetchMock(fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty state when no project/drawing is selected", () => {
    renderObjects("/objects");
    expect(screen.getByTestId("objects-no-project")).toBeInTheDocument();
    expect(screen.getByText(/Choose a project on the Dashboard/i)).toBeInTheDocument();
  });

  it("loads the master drawing and renders overlays scoped to the run param", async () => {
    installDefaultFetchMock(fetchMock, {
      overlays: [SAMPLE_OVERLAY],
      onOverlayRequest: (url) => {
        expect(url).toContain(`inspection_run_id=${RUN_ID}`);
      },
    });

    renderObjects(
      `/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}&run=${RUN_ID}`,
    );

    await waitForDrawingCanvasReady();
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("falls back to the latest-run overlay fetch when no run param is present", async () => {
    let latestRunFetchCount = 0;

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = requestUrl(input);

      if (url.includes("/inspections/runs") && url.includes("limit=1")) {
        latestRunFetchCount += 1;
      }

      if (url.includes("/api/projects") && url.endsWith("/api/projects")) {
        return jsonResponse({
          items: [{ id: PROJECT_ID, name: "Project One", company_id: 1 }],
        });
      }
      if (url.includes("/api/objects")) return jsonResponse([]);
      if (url.includes(`/api/projects/${PROJECT_ID}/drawings`) && !url.includes("/drawings/")) {
        return jsonResponse({
          drawings: [{ id: DRAWING_ID, name: "Sheet A", source: "master" }],
        });
      }
      if (url.includes(`/api/projects/${PROJECT_ID}/dashboard/summary`)) {
        return jsonResponse({
          project: { id: PROJECT_ID, name: "Project One", masterDrawingId: DRAWING_ID },
          masterDrawing: { id: DRAWING_ID, name: "Sheet A" },
        });
      }
      if (
        url.includes(`/api/projects/${PROJECT_ID}/drawings/${DRAWING_ID}`) &&
        !url.includes("/overlays") &&
        !url.includes("/region")
      ) {
        return jsonResponse(SAMPLE_MASTER_DRAWING);
      }
      if (url.includes("/overlays")) {
        expect(url).toContain(`inspection_run_id=${RUN_ID}`);
        return jsonResponse([SAMPLE_OVERLAY]);
      }
      if (url.includes("/region-inspection-summary")) {
        return jsonResponse({ items: [] });
      }
      if (url.includes("/inspections/runs") && url.includes("limit=1")) {
        return jsonResponse({
          items: [{ id: RUN_ID, master_drawing_id: DRAWING_ID, status: "complete" }],
          total: 1,
          limit: 1,
          offset: 0,
        });
      }
      if (url.includes("/inspections/runs")) return jsonResponse(EMPTY_RUN_LIST);
      if (url.includes("/evidence")) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitFor(() => expect(latestRunFetchCount).toBeGreaterThan(0));
    await waitForDrawingCanvasReady();
    expect(screen.getByTestId("overlay-rect-0")).toBeInTheDocument();
  });

  it("shows a no-findings message when overlays come back empty", async () => {
    installDefaultFetchMock(fetchMock, { overlays: [], latestRunId: null });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitForDrawingCanvasReady();
    expect(screen.getByText(/No inspection findings yet/i)).toBeInTheDocument();
  });

  it("shows an error state if the master drawing fails to load", async () => {
    installDefaultFetchMock(fetchMock, { masterDrawing: "error" });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitFor(() => {
      expect(screen.getByText("Could not load drawing")).toBeInTheDocument();
    });
    expect(screen.getByText("Not found")).toBeInTheDocument();
  });

  it("renders a bold region shape from the region inspection summary", async () => {
    installDefaultFetchMock(fetchMock, {
      overlays: [],
      regionSummary: [makeSummaryEntry()],
    });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitForDrawingCanvasReady();
    expect(screen.getByTestId("region-shape")).toBeInTheDocument();
    expect(screen.getByTestId("region-shape")).toHaveAttribute("data-region-state", "inspected");
  });

  it("the 'Show inspectable areas' toggle reveals hidden regions as faint outlines", async () => {
    installDefaultFetchMock(fetchMock, {
      overlays: [],
      regionSummary: [makeSummaryEntry({ state: "hidden" })],
    });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitFor(() => expect(screen.getByText("Sheet A")).toBeInTheDocument());
    expect(screen.queryByTestId("region-shape")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("show-inspectable-areas-toggle"));

    await waitForDrawingCanvasReady();

    await waitFor(() => expect(screen.getByTestId("region-shape")).toBeInTheDocument());
    expect(screen.getByTestId("region-shape")).toHaveAttribute(
      "data-region-state",
      "setup_faint",
    );
  });

  it("clicking 'Manage regions' switches to the region editor", async () => {
    installDefaultFetchMock(fetchMock);

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitFor(() => expect(screen.getByText("Sheet A")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("manage-regions-button"));

    expect(await screen.findByTestId("region-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("drawing-comparison-workspace")).not.toBeInTheDocument();
  });

  it("clicking a region shape updates the ?region= URL param (PR5 click sync)", async () => {
    installDefaultFetchMock(fetchMock, {
      overlays: [],
      regionSummary: [makeSummaryEntry()],
    });

    renderObjects(`/objects?projectId=${PROJECT_ID}&drawingId=${DRAWING_ID}`);

    await waitForDrawingCanvasReady();
    expect(screen.queryByTestId("objects-focused-region")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("region-shape"));

    await waitFor(() => {
      expect(screen.getByTestId("objects-focused-region")).toHaveTextContent(
        "Focused region: 1",
      );
    });
  });
});
