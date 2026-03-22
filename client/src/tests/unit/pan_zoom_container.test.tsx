import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";

describe("PanZoomContainer", () => {
  it("renders children", () => {
    render(
      <PanZoomContainer>
        <div>Test Content</div>
      </PanZoomContainer>
    );

    expect(screen.getByText("Test Content")).toBeInTheDocument();
    expect(screen.getByTestId("pan-zoom-container")).toBeInTheDocument();
    expect(screen.getByTestId("pan-zoom-content")).toBeInTheDocument();
  });

  it("changes zoom on wheel", () => {
    render(
      <PanZoomContainer>
        <div>Zoom Content</div>
      </PanZoomContainer>
    );

    const container = screen.getByTestId("pan-zoom-container");
    const content = screen.getByTestId("pan-zoom-content");

    fireEvent.wheel(container, {
      deltaY: -400,
      clientX: 100,
      clientY: 100,
    });

    expect(content.getAttribute("style")).toContain("scale(");
    expect(screen.getByText(/Zoom:/)).not.toHaveTextContent("100%");
  });

  it("resets view", () => {
    render(
      <PanZoomContainer>
        <div>Reset Content</div>
      </PanZoomContainer>
    );

    const container = screen.getByTestId("pan-zoom-container");
    fireEvent.wheel(container, {
      deltaY: -400,
      clientX: 100,
      clientY: 100,
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));

    expect(screen.getByText(/Zoom:/)).toHaveTextContent("100%");
  });
});
