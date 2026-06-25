import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

import InspectionUploadForm from "@/components/inspections/inspection_upload_form";

const createInspectionRunMock = vi.fn();
const uploadInspectionRunEvidenceMock = vi.fn();
const refreshInspectionWorkspaceQueriesMock = vi.fn();

vi.mock("@/lib/api/inspections", () => ({
  createInspectionRun: (...args: unknown[]) => createInspectionRunMock(...args),
  uploadInspectionRunEvidence: (...args: unknown[]) =>
    uploadInspectionRunEvidenceMock(...args),
}));

vi.mock("@/lib/api/inspection_runs", () => ({
  refreshInspectionWorkspaceQueries: (...args: unknown[]) =>
    refreshInspectionWorkspaceQueriesMock(...args),
}));

vi.mock("@/lib/api/drawings", () => ({
  projectDrawingsQueryKey: (projectId: number) => ["project-drawings", projectId],
  fetchProjectDrawings: vi.fn().mockResolvedValue({
    drawings: [
      { id: 10, name: "Level 1", source: "master" },
      { id: 11, name: "Level 2", source: "master" },
    ],
  }),
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

  it("requires a master drawing before upload", async () => {
    renderForm(<InspectionUploadForm projectId={2} />);

    await screen.findByTestId("inspection-upload-master-drawing");
    expect(screen.getByTestId("inspection-upload-submit")).toBeDisabled();
  });

  it("creates a run and uploads evidence for the selected master drawing", async () => {
    const onUploaded = vi.fn();
    renderForm(
      <InspectionUploadForm
        projectId={2}
        initialMasterDrawingId="10"
        onUploaded={onUploaded}
      />,
    );

    await screen.findByTestId("inspection-upload-submit");
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
});
