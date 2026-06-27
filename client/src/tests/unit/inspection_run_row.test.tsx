/**
 * client/src/tests/unit/inspection_run_row.test.tsx
 *
 * PR5: history rows show linked region label + "View region" deep link;
 * panel rows remain selectable without region chrome.
 */

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
    id: 1,
    project_id: 1,
    master_drawing_id: 1,
    status: "complete",
    inspection_type: "Roof QA",
    evidence_id: null,
    created_at: "2026-06-24T00:00:00Z",
    updated_at: "2026-06-24T00:00:00Z",
    started_at: null,
    completed_at: "2026-06-24T00:05:00Z",
    error_message: null,
    ...overrides,
  };
}

function renderHistoryRow(run: InspectionRunRowRun, projectId: string) {
  return render(
    <ul>
      <InspectionRunRow run={run} projectId={projectId} />
    </ul>,
  );
}

describe("InspectionRunRow", () => {
  it("renders without a region label or link when the run has no region", () => {
    renderHistoryRow(buildRun({ region_id: null, region_label: null }), "p1");
    expect(screen.queryByTestId("inspection-run-region-label")).not.toBeInTheDocument();
    expect(screen.queryByTestId("view-region-link")).not.toBeInTheDocument();
  });

  it("shows the region label and a view-region link when the run has a linked region", () => {
    renderHistoryRow(
      buildRun({ region_id: 1, region_label: "Storm Drain #44" }),
      "p1",
    );
    expect(screen.getByTestId("inspection-run-region-label")).toHaveTextContent("Storm Drain #44");
    expect(screen.getByTestId("view-region-link")).toBeInTheDocument();
  });

  it("the view-region link includes projectId, drawingId, run, and region in the URL", () => {
    renderHistoryRow(
      buildRun({
        id: 42,
        master_drawing_id: 9,
        region_id: 5,
        region_label: "Roof",
      }),
      "p7",
    );
    const link = screen.getByTestId("view-region-link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/objects?projectId=p7&drawingId=9&run=42&region=5");
  });

  it("always renders the plain view-on-drawing link regardless of region presence", () => {
    renderHistoryRow(buildRun(), "p1");
    expect(screen.getByTestId("view-on-drawing-link")).toBeInTheDocument();
  });

  it("shows finding counts and review-needed text alongside the region label", () => {
    renderHistoryRow(
      buildRun({
        overlays_created: 2,
        unresolved_count: 1,
        region_id: 1,
        region_label: "Utility MR",
      }),
      "p1",
    );
    const row = screen.getByTestId("inspection-run-row");
    expect(row).toHaveTextContent("2 findings placed");
    expect(row).toHaveTextContent("1 needs review");
    expect(row).toHaveTextContent("Utility MR");
  });
});

describe("InspectionRunRow panel mode", () => {
  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();

    render(
      <ul>
        <InspectionRunRow run={buildRun({ id: 15 })} onSelect={onSelect} />
      </ul>,
    );

    fireEvent.click(screen.getByTestId("inspection-run-row-15"));
    expect(onSelect).toHaveBeenCalledWith(15);
  });
});
