import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InspectionRunProgressPanel from "@/components/drawing-workspace/inspection_run_progress_panel";

describe("InspectionRunProgressPanel", () => {
  it("shows inspecting placeholder while active and progress not loaded yet", () => {
    render(
      <InspectionRunProgressPanel progress={undefined} isLoading={false} isActive />,
    );

    expect(screen.getByTestId("inspection-run-progress-panel")).toHaveTextContent(
      "Inspecting…",
    );
  });

  it("shows page progress when payload arrives", () => {
    render(
      <InspectionRunProgressPanel
        isActive
        progress={{
          run_id: 1,
          current: { label: "Reading page 2 of 8" },
          steps: [],
        }}
      />,
    );

    expect(screen.getByText("Reading page 2 of 8")).toBeInTheDocument();
  });
});
