import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegionDrawCanvas } from "@/components/drawing-workspace/region_draw_canvas";

function mockRect(element: HTMLElement, width: number, height: number) {
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    width,
    height,
    top: 0,
    left: 0,
    bottom: height,
    right: width,
    toJSON: () => ({}),
  });
}

describe("RegionDrawCanvas", () => {
  it("emits normalized rect geometry after a drag", () => {
    const onGeometryComplete = vi.fn();

    render(
      <RegionDrawCanvas
        imageUrl="/drawing.png"
        pageWidth={1000}
        pageHeight={800}
        tool="rect"
        onGeometryComplete={onGeometryComplete}
      />,
    );

    const surface = screen.getByTestId("region-draw-surface");
    mockRect(surface, 500, 400);

    fireEvent.mouseDown(surface, { clientX: 50, clientY: 40 });
    fireEvent.mouseMove(surface, { clientX: 250, clientY: 200 });
    fireEvent.mouseUp(surface);

    expect(onGeometryComplete).toHaveBeenCalledTimes(1);
    expect(onGeometryComplete.mock.calls[0]?.[0]).toEqual({
      shape: "rect",
      geometry: {
        type: "rect",
        x: 0.1,
        y: 0.1,
        width: 0.4,
        height: 0.4,
      },
    });
  });

  it("emits polygon draft on double-click after three clicks", () => {
    const onGeometryComplete = vi.fn();

    render(
      <RegionDrawCanvas
        imageUrl="/drawing.png"
        pageWidth={1000}
        pageHeight={1000}
        tool="polygon"
        onGeometryComplete={onGeometryComplete}
      />,
    );

    const surface = screen.getByTestId("region-draw-surface");
    mockRect(surface, 500, 500);

    fireEvent.click(surface, { clientX: 100, clientY: 275 });
    fireEvent.click(surface, { clientX: 325, clientY: 275 });
    fireEvent.click(surface, { clientX: 325, clientY: 375 });
    fireEvent.dblClick(surface);

    expect(onGeometryComplete).toHaveBeenCalledTimes(1);
    expect(onGeometryComplete.mock.calls[0]?.[0]).toMatchObject({
      shape: "polygon",
      geometry: {
        type: "rect",
        x: 0.2,
        y: 0.55,
        width: 0.45,
        height: 0.2,
      },
    });
  });

  it("shows cancel while drawing and clears on click", () => {
    const onCancel = vi.fn();

    render(
      <RegionDrawCanvas
        imageUrl="/drawing.png"
        pageWidth={1000}
        pageHeight={800}
        tool="rect"
        onGeometryComplete={vi.fn()}
        onCancel={onCancel}
      />,
    );

    const surface = screen.getByTestId("region-draw-surface");
    mockRect(surface, 500, 400);

    fireEvent.mouseDown(surface, { clientX: 10, clientY: 10 });
    fireEvent.mouseMove(surface, { clientX: 100, clientY: 100 });

    fireEvent.click(screen.getByTestId("region-draw-cancel-button"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("region-draw-cancel-button")).not.toBeInTheDocument();
  });
});
