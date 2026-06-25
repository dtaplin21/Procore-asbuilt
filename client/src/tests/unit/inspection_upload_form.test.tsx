import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

import InspectionUploadForm from "@/components/inspections/inspection_upload_form";

const createInspectionRunMock = vi.fn();
const uploadInspectionRunEvidenceMock = vi.fn();
const refreshInspectionWorkspaceQueriesMock = vi.fn();
const fetchProjectDashboardSummaryMock = vi.fn();

vi.mock("@/lib/api/inspections", () => ({
  createInspectionRun: (...args: unknown[]) => createInspectionRunMock(...args),
  uploadInspectionRunEvidence: (...args: unknown[]) =>
    uploadInspectionRunEvidenceMock(...args),
}));

vi.mock("@/lib/api/inspection_runs", () => ({
  refreshInspectionWorkspaceQueries: (...args: unknown[]) =>
    refreshInspectionWorkspaceQueriesMock(...args),
}));

vi.mock("@/lib/api/projects", () => ({
  fetchProjectDashboardSummary: (...args: unknown[]) =>
    fetchProjectDashboardSummaryMock(...args),
}));

function renderForm(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("InspectionUploadForm", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    createInspectionRunMock.mockReset();
    uploadInspectionRunEvidenceMock.mockReset();
    refreshInspectionWorkspaceQueriesMock.mockReset();
    fetchProjectDashboardSummaryMock.mockReset();
    fetchProjectDashboardSummaryMock.mockResolvedValue({
      project: { id: 2, name: "Test", masterDrawingId: 10 },
      masterDrawing: { id: 10, name: "Level 1", updated_at: "2026-01-01T00:00:00Z" },
    });
    createInspectionRunMock.mockResolvedValue({
      id: "7",
      projectId: "2",
      masterDrawingId: "10",
      status: "complete",
      createdAt: "2026-01-01T00:00:00Z",
    });
    uploadInspectionRunEvidenceMock.mockResolvedValue({
      evidence_id: "99",
      overlays_created: 2,
      unresolved_count: 0,
      untagged_region_count: 0,
      overlay_ids: ["1", "2"],
    });
    refreshInspectionWorkspaceQueriesMock.mockResolvedValue(undefined);
  });

  it("disables upload when the project has no canonical master", async () => {
    fetchProjectDashboardSummaryMock.mockResolvedValue({
      project: { id: 2, name: "Test", masterDrawingId: null },
      masterDrawing: null,
    });

    renderForm(<InspectionUploadForm projectId={2} />);

    await screen.findByTestId("inspection-upload-master-label");
    expect(screen.getByTestId("inspection-upload-submit")).toBeDisabled();
    expect(
      screen.getByText(/No canonical master sheet — upload a drawing on the Dashboard first/i),
    ).toBeInTheDocument();
  });

  it("shows the canonical master sheet and uploads against it", async () => {
    const onUploaded = vi.fn();
    renderForm(
      <InspectionUploadForm projectId={2} onUploaded={onUploaded} />,
    );

    await screen.findByText("Level 1");
    expect(screen.getByTestId("inspection-upload-submit")).not.toBeDisabled();

    const file = new File(["pdf"], "inspection.pdf", { type: "application/pdf" });
    const input = screen.getByTestId("inspection-upload-file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(createInspectionRunMock).toHaveBeenCalledWith({
        projectId: "2",
        masterDrawingId: "10",
        skipPipeline: true,
      });
    });

    await waitFor(() => {
      expect(uploadInspectionRunEvidenceMock).toHaveBeenCalledWith({
        projectId: "2",
        runId: "7",
        masterDrawingId: "10",
        file,
      });
    });

    expect(onUploaded).toHaveBeenCalledWith(
      expect.objectContaining({
        runId: "7",
        masterDrawingId: "10",
      }),
    );
  });

  it("honors initialMasterDrawingId override", async () => {
    renderForm(
      <InspectionUploadForm projectId={2} initialMasterDrawingId="11" />,
    );

    await screen.findByText("Drawing 11");
    expect(screen.getByTestId("inspection-upload-submit")).not.toBeDisabled();
  });
});
