/**
 * Phase 5 — active project navigation, sidebar sync, and read-only page behavior.
 */
import { beforeAll, beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import Dashboard from "@/pages/dashboard";
import Inspections from "@/pages/inspections";
import Objects from "@/pages/objects";
import InspectionUploadForm from "@/components/inspections/inspection_upload_form";
import { useActiveProject } from "@/contexts/active_project_context";
import {
  ACTIVE_PROJECT_ID_STORAGE_KEY,
  getActiveProjectIdFromStorage,
} from "@/lib/active_project";
import { getObjectsSidebarNav } from "@/lib/workspace-return-path";
import {
  createTestQueryClient,
  renderActiveProjectPage,
  renderWithActiveProjectRoutes,
} from "@/tests/helpers/render_with_active_project";

const fetchProjectDrawingsMock = vi.fn();
const fetchProjectDashboardSummaryMock = vi.fn();
const fetchMasterDrawingMock = vi.fn();
const createInspectionRunMock = vi.fn();
const uploadInspectionRunEvidenceMock = vi.fn();

vi.mock("@/components/drawings/DrawingViewer", () => ({
  default: () => <div data-testid="drawing-viewer-mock" />,
}));

vi.mock("@/components/ProcoreWritebackPanel", () => ({
  ProcoreWritebackPanel: () => <div data-testid="procore-writeback-mock" />,
}));

vi.mock("@/components/drawing-workspace/inspection_runs_panel", () => ({
  default: () => <div data-testid="inspection-runs-panel-mock" />,
}));

vi.mock("@/components/JobQueueList", () => ({
  default: () => null,
}));

vi.mock("@/components/drawing-workspace/UploadDrawingModal", () => ({
  UploadDrawingModal: () => null,
}));

vi.mock("@/components/procore-status", () => ({
  ProcoreStatus: () => null,
}));

vi.mock("@/components/drawing-workspace/inspection_run_row", () => ({
  default: () => null,
}));

vi.mock("@/hooks/use-inspection-runs", () => ({
  useInspectionRuns: () => ({
    data: { items: [], total: 0, limit: 50, offset: 0 },
    isLoading: false,
    isError: false,
  }),
  useDrawingOverlays: () => ({
    data: [],
    isLoading: false,
  }),
}));

vi.mock("@/lib/api/drawings", () => ({
  projectDrawingsQueryKey: (projectId: number) => ["project-drawings", projectId],
  fetchProjectDrawings: (...args: unknown[]) => fetchProjectDrawingsMock(...args),
}));

vi.mock("@/lib/api/projects", () => ({
  fetchProjectDashboardSummary: (...args: unknown[]) =>
    fetchProjectDashboardSummaryMock(...args),
}));

vi.mock("@/lib/api/drawing_workspace", () => ({
  fetchMasterDrawing: (...args: unknown[]) => fetchMasterDrawingMock(...args),
}));

vi.mock("@/lib/api/inspections", () => ({
  createInspectionRun: (...args: unknown[]) => createInspectionRunMock(...args),
  uploadInspectionRunEvidence: (...args: unknown[]) =>
    uploadInspectionRunEvidenceMock(...args),
}));

vi.mock("@/lib/api/inspection_runs", () => ({
  refreshInspectionWorkspaceQueries: vi.fn().mockResolvedValue(undefined),
}));

function ActiveProjectProbe() {
  const { projectId } = useActiveProject();
  return (
    <span data-testid="active-project-id">{projectId ?? "none"}</span>
  );
}

function NavigateToInspections() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      data-testid="go-inspections"
      onClick={() => navigate("/inspections")}
    >
      Inspections
    </button>
  );
}

function DrawingIdUrlProbe() {
  const [params] = useSearchParams();
  return (
    <span data-testid="url-drawing-id">{params.get("drawingId") ?? "none"}</span>
  );
}

function seedDashboardQueries(client: ReturnType<typeof createTestQueryClient>) {
  client.setQueryData(["/api/projects"], {
    items: [
      { id: 1, name: "Project One", company_id: 1 },
      { id: 3, name: "Project Three", company_id: 1 },
    ],
  });
  client.setQueryData(["/api/dashboard/stats"], {
    criticalAlerts: 0,
  });
  client.setQueryData(["projectFindings", "1"], { items: [], total: 0 });
  client.setQueryData(["projectFindings", "3"], { items: [], total: 0 });
  client.setQueryData(["projectJobs", "1"], { items: [], total: 0 });
  client.setQueryData(["projectJobs", "3"], { items: [], total: 0 });
  client.setQueryData(["project-dashboard-summary", "1", null, null], {
    project: { id: 1, name: "Project One", company_id: 1, masterDrawingId: 10 },
    kpis: {
      total_findings: 0,
      open_findings: 0,
      drawings_count: 1,
      evidence_count: 0,
      inspections_count: 0,
    },
  });
  client.setQueryData(["project-dashboard-summary", "3", null, null], {
    project: { id: 3, name: "Project Three", company_id: 1, masterDrawingId: 30 },
    kpis: {
      total_findings: 0,
      open_findings: 0,
      drawings_count: 1,
      evidence_count: 0,
      inspections_count: 0,
    },
  });
  client.setQueryData(["/api/objects"], []);
}

describe("Phase 5 — active project navigation", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    sessionStorage.clear();
    fetchProjectDrawingsMock.mockReset();
    fetchProjectDashboardSummaryMock.mockReset();
    fetchMasterDrawingMock.mockReset();
    createInspectionRunMock.mockReset();
    uploadInspectionRunEvidenceMock.mockReset();

    fetchProjectDrawingsMock.mockImplementation(async (projectId: number) => ({
      drawings:
        projectId === 5
          ? [{ id: 50, name: "Project Five Sheet", source: "master" }]
          : [],
    }));

    fetchProjectDashboardSummaryMock.mockImplementation(async (projectId: number) => ({
      project: {
        id: projectId,
        name: `Project ${projectId}`,
        masterDrawingId: projectId === 5 ? 50 : null,
      },
      masterDrawing:
        projectId === 5
          ? {
              id: 50,
              name: "Project Five Sheet",
              updated_at: "2026-01-01T00:00:00Z",
            }
          : null,
    }));

    createInspectionRunMock.mockResolvedValue({
      id: "7",
      projectId: "2",
      masterDrawingId: "10",
      status: "complete",
    });
    uploadInspectionRunEvidenceMock.mockResolvedValue({
      overlays_created: 1,
      unresolved_count: 0,
      untagged_region_count: 0,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("Objects ?projectId=5 sets context and Inspections sees the same project", async () => {
    renderWithActiveProjectRoutes("/objects?projectId=5", [
      {
        path: "/objects",
        element: (
          <>
            <ActiveProjectProbe />
            <NavigateToInspections />
          </>
        ),
      },
      {
        path: "/inspections",
        element: (
          <>
            <ActiveProjectProbe />
            <Inspections />
          </>
        ),
      },
    ]);

    await waitFor(() => {
      expect(screen.getByTestId("active-project-id")).toHaveTextContent("5");
    });

    expect(getActiveProjectIdFromStorage()).toBe(5);

    fireEvent.click(screen.getByTestId("go-inspections"));

    await waitFor(() => {
      expect(screen.getByTestId("active-project-id")).toHaveTextContent("5");
    });
  });

  it("Dashboard project change persists project 3 and Objects sidebar href includes it", async () => {
    const queryClient = createTestQueryClient();
    seedDashboardQueries(queryClient);

    renderActiveProjectPage(
      "/",
      "/",
      <Dashboard
        procoreConnection={{
          connected: false,
          syncStatus: "idle",
          projectsLinked: 0,
        }}
      />,
      { queryClient },
    );

    await waitFor(() => {
      expect(screen.getByTestId("project-selector")).toHaveValue("1");
    });

    fireEvent.change(screen.getByTestId("project-selector"), {
      target: { value: "3" },
    });

    await waitFor(() => {
      expect(getActiveProjectIdFromStorage()).toBe(3);
    });

    expect(getObjectsSidebarNav().href).toContain("projectId=3");
  });
});

describe("Phase 5 — read-only pages and canonical master", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    sessionStorage.clear();
    fetchProjectDrawingsMock.mockReset();
    fetchProjectDashboardSummaryMock.mockReset();
    fetchMasterDrawingMock.mockReset();
    createInspectionRunMock.mockReset();

    fetchProjectDrawingsMock.mockResolvedValue({
      drawings: [{ id: 10, name: "Canonical Sheet", source: "master" }],
    });
    fetchProjectDashboardSummaryMock.mockResolvedValue({
      project: { id: 2, name: "Project Two", masterDrawingId: 10 },
      masterDrawing: {
        id: 10,
        name: "Canonical Sheet",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
    fetchMasterDrawingMock.mockResolvedValue({
      id: 10,
      name: "Canonical Sheet",
      projectId: 2,
    });
    createInspectionRunMock.mockResolvedValue({
      id: "7",
      projectId: "2",
      masterDrawingId: "10",
      status: "complete",
    });
    uploadInspectionRunEvidenceMock.mockResolvedValue({
      overlays_created: 1,
      unresolved_count: 0,
      untagged_region_count: 0,
    });
  });

  it("Inspections and Objects do not render project or master picker dropdowns", async () => {
    sessionStorage.setItem(ACTIVE_PROJECT_ID_STORAGE_KEY, "2");

    const { unmount: unmountInspections } = renderActiveProjectPage(
      "/inspections",
      "/inspections",
      <Inspections />,
    );
    expect(screen.queryByTestId("inspections-project-select")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("inspection-upload-master-drawing"),
    ).not.toBeInTheDocument();
    unmountInspections();

    renderActiveProjectPage("/objects", "/objects?projectId=2", <Objects />);
    expect(screen.queryByTestId("select-objects-project")).not.toBeInTheDocument();
    expect(screen.queryByTestId("select-objects-master-drawing")).not.toBeInTheDocument();
  });

  it("upload uses canonical master without user selection", async () => {
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <InspectionUploadForm projectId={2} />
      </QueryClientProvider>,
    );

    await screen.findByText("Canonical Sheet");
    expect(screen.getByTestId("inspection-upload-submit")).not.toBeDisabled();
    expect(
      screen.queryByTestId("inspection-upload-master-drawing"),
    ).not.toBeInTheDocument();

    const file = new File(["pdf"], "inspection.pdf", { type: "application/pdf" });
    fireEvent.change(
      screen.getByTestId("inspection-upload-file-input") as HTMLInputElement,
      { target: { files: [file] } },
    );

    await waitFor(() => {
      expect(createInspectionRunMock).toHaveBeenCalledWith({
        projectId: "2",
        masterDrawingId: "10",
        skipPipeline: true,
      });
    });
  });

  it("Objects defaults to canonical master in the URL when drawingId is absent", async () => {
    sessionStorage.setItem(ACTIVE_PROJECT_ID_STORAGE_KEY, "2");

    renderActiveProjectPage(
      "/objects",
      "/objects?projectId=2",
      <Objects />,
      { siblings: <DrawingIdUrlProbe /> },
    );

    await waitFor(() => {
      expect(screen.getByTestId("url-drawing-id")).toHaveTextContent("10");
    });

    await waitFor(() => {
      expect(screen.getByTestId("objects-master-header")).toHaveTextContent(
        "Canonical Sheet",
      );
    });
  });
});
