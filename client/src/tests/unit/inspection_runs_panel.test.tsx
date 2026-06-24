import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent } from "@testing-library/react";
import type { ReactElement } from "react";
import type { EvidenceRecordResponse } from "@shared/schema";

import InspectionRunsPanel from "@/components/drawing-workspace/inspection_runs_panel";

const runMutate = vi.fn();

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
}));

vi.mock("@/components/drawing-workspace/evidence_upload_field", () => ({
  default: ({
    onUploaded,
  }: {
    onUploaded: (evidence: EvidenceRecordResponse) => void;
  }) => (
    <button
      type="button"
      data-testid="mock-evidence-upload-success"
      onClick={() =>
        onUploaded({
          id: 99,
          type: "inspection_doc",
          title: "Site photo",
          created_at: "2026-01-01T12:00:00Z",
        })
      }
    >
      Mock upload
    </button>
  ),
}));

function renderPanel(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("InspectionRunsPanel", () => {
  it("renders runs and run inspection control", () => {
    renderPanel(
      <InspectionRunsPanel projectId={2} masterDrawingId={10} />
    );

    expect(screen.getByTestId("inspection-runs-panel")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-runs-run")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-run-row-1")).toBeInTheDocument();
  });

  it("triggers useRunInspection after evidence upload success", () => {
    runMutate.mockClear();
    renderPanel(
      <InspectionRunsPanel projectId={2} masterDrawingId={10} />
    );

    fireEvent.click(screen.getByTestId("mock-evidence-upload-success"));

    expect(runMutate).toHaveBeenCalledWith(
      { master_drawing_id: 10, evidence_id: 99 },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });
});
