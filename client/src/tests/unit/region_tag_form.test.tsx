import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegionTagForm } from "@/components/drawing-workspace/region_tag_form";

describe("RegionTagForm", () => {
  it("submits parsed label and comma-separated tags", () => {
    const onSave = vi.fn();

    render(
      <RegionTagForm
        initialLabel="Utility MR"
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByTestId("region-inspection-types-input"), {
      target: { value: "Rough In, Hydrostatic Test" },
    });
    fireEvent.change(screen.getByTestId("region-locations-input"), {
      target: { value: "Utility MR" },
    });
    fireEvent.click(screen.getByTestId("region-tag-form-save"));

    expect(onSave).toHaveBeenCalledWith({
      label: "Utility MR",
      inspectionTypeTags: ["Rough In", "Hydrostatic Test"],
      locationTags: ["Utility MR"],
    });
  });

  it("derives label from first location when label is blank", () => {
    const onSave = vi.fn();

    render(<RegionTagForm onSave={onSave} />);

    fireEvent.change(screen.getByTestId("region-locations-input"), {
      target: { value: "Roof Area" },
    });
    fireEvent.click(screen.getByTestId("region-tag-form-save"));

    expect(onSave).toHaveBeenCalledWith({
      label: "Roof Area",
      inspectionTypeTags: [],
      locationTags: ["Roof Area"],
    });
  });

  it("calls onCancel from the cancel button", () => {
    const onCancel = vi.fn();

    render(<RegionTagForm onSave={vi.fn()} onCancel={onCancel} />);

    fireEvent.click(screen.getByTestId("region-tag-form-cancel"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
