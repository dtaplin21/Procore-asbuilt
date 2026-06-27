import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import InspectionRunRow from "@/components/drawing-workspace/inspection_run_row";
import type { InspectionRunRowRun } from "@/components/drawing-workspace/inspection_run_row";

vi.mock("@/lib/api/inspections", () => ({
  evidenceFileDownloadUrl: (projectId: string, evidenceFileId: string) =>
    `/api/projects/${projectId}/evidence/${evidenceFileId}/file`,
}));

function buildRun(overrides: Partial<InspectionRunRowRun> = {}): InspectionRunRowRun {
  return {
    id: 15,
    project_id: 2,
    master_drawing_id: 8,
    status: "complete",
    inspection_type: "Roof QA",
    evidence_id: 99,
    created_at: "2026-06-01T12:00:00.000Z",
    updated_at: "2026-06-01T12:05:00.000Z",
    started_at: null,
    completed_at: "2026-06-01T12:05:00.000Z",
    error_message: null,
    overlays_created: 3,
    unresolved_count: 1,
    region_id: 7,
    region_label: "Roof MR",
    evidence_title: "Roof inspection report",
    ...overrides,
  };
}

describe("InspectionRunRow history mode", () => {
  it("shows evidence title, region label, and action links", () => {
    render(
      <ul>
        <InspectionRunRow run={buildRun()} projectId="2" />
      </ul>,
    );

    expect(screen.getByText("Roof inspection report")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-run-region-label")).toHaveTextContent("Roof MR");
    expect(screen.getByTestId("view-on-drawing-link")).toHaveAttribute(
      "href",
      "/objects?projectId=2&drawingId=8&run=15",
    );
    expect(screen.getByTestId("view-region-link")).toHaveAttribute(
      "href",
      "/objects?projectId=2&drawingId=8&run=15&region=7",
    );
    expect(screen.getByTestId("evidence-file-link")).toHaveAttribute(
      "href",
      "/api/projects/2/evidence/99/file",
    );
  });

  it("omits region link when run has no region", () => {
    render(
      <ul>
        <InspectionRunRow run={buildRun({ region_id: null, region_label: null })} projectId="2" />
      </ul>,
    );

    expect(screen.queryByTestId("view-region-link")).not.toBeInTheDocument();
  });
});

describe("InspectionRunRow panel mode", () => {
  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();

    render(
      <ul>
        <InspectionRunRow run={buildRun()} onSelect={onSelect} />
      </ul>,
    );

    fireEvent.click(screen.getByTestId("inspection-run-row-15"));
    expect(onSelect).toHaveBeenCalledWith(15);
  });
});
