import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

import InspectionRunsPanel from "@/components/drawing-workspace/inspection_runs_panel";

const runMutate = vi.fn();
const createRunAsync = vi.fn();
const uploadRunEvidenceAsync = vi.fn();

vi.mock("@/hooks/use-inspection-runs", () => ({
  useInspectionRuns: () => ({
    data: {
      items: [
        {
          id: 1,
          project_id: 2,
          master_drawing_id: 10,
          evidence_id: 5,
          inspection_type: "visual",
          status: "complete",
          started_at: null,
          completed_at: "2026-01-01T12:00:00Z",
          error_message: null,
          created_at: "2026-01-01T12:00:00Z",
          updated_at: "2026-01-01T12:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    },
    isLoading: false,
    isError: false,
  }),
  useRunInspection: () => ({
    mutate: runMutate,
    isPending: false,
  }),
  useCreateInspectionRun: () => ({
    mutateAsync: createRunAsync,
    isPending: false,
  }),
  useUploadInspectionRunEvidence: () => ({
    mutateAsync: uploadRunEvidenceAsync,
    isPending: false,
  }),
  useDrawingOverlays: () => ({
    data: [
      {
        id: 42,
        master_drawing_id: 10,
        inspection_run_id: 1,
        diff_id: null,
        geometry: { type: "rect", x: 0.1, y: 0.1, width: 0.2, height: 0.2, label: "Final — Roof" },
        status: "fail",
        label: "Final — Roof",
        severity: "high",
        meta: null,
        created_at: "2026-01-01T12:00:00Z",
      },
    ],
    isLoading: false,
  }),
}));

function renderPanel(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("InspectionRunsPanel", () => {
  beforeEach(() => {
    runMutate.mockClear();
    createRunAsync.mockReset();
    uploadRunEvidenceAsync.mockReset();
    createRunAsync.mockResolvedValue({ id: 7, status: "queued" });
    uploadRunEvidenceAsync.mockResolvedValue({
      evidence_id: 99,
      overlays_created: 1,
      unresolved_count: 0,
      untagged_region_count: 0,
      overlay_ids: [42],
    });
  });

  it("renders runs and upload control", () => {
    renderPanel(
      <InspectionRunsPanel projectId={2} masterDrawingId={10} selectedRunId={1} />
    );

    expect(screen.getByTestId("inspection-runs-panel")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-run-evidence-upload")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-run-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-run-overlay-list")).toBeInTheDocument();
    expect(screen.getByText("Final — Roof")).toBeInTheDocument();
  });

  it("uploads evidence to the document pipeline for the selected run", async () => {
    const onSelectRun = vi.fn();
    renderPanel(
      <InspectionRunsPanel
        projectId={2}
        masterDrawingId={10}
        selectedRunId={1}
        onSelectRun={onSelectRun}
      />
    );

    const input = screen.getByTestId("inspection-run-evidence-file-input") as HTMLInputElement;
    const file = new File(["pdf"], "report.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadRunEvidenceAsync).toHaveBeenCalledWith({
        inspectionRunId: 1,
        file,
        masterDrawingId: 10,
      });
    });

    expect(createRunAsync).not.toHaveBeenCalled();
    expect(onSelectRun).toHaveBeenCalledWith(1);
  });

  it("creates a deferred run when uploading without a selection", async () => {
    renderPanel(<InspectionRunsPanel projectId={2} masterDrawingId={10} selectedRunId={null} />);

    const input = screen.getByTestId("inspection-run-evidence-file-input") as HTMLInputElement;
    const file = new File(["pdf"], "report.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(createRunAsync).toHaveBeenCalledWith({
        master_drawing_id: 10,
        skip_pipeline: true,
      });
    });

    await waitFor(() => {
      expect(uploadRunEvidenceAsync).toHaveBeenCalledWith({
        inspectionRunId: 7,
        file,
        masterDrawingId: 10,
      });
    });
  });
});
