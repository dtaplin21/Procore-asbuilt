import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";

class TestPointerEvent extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 0;
  }
}

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

  it("pans the sheet when the pointer drags", () => {
    render(
      <PanZoomContainer>
        <div>Drag Content</div>
      </PanZoomContainer>
    );

    vi.stubGlobal("PointerEvent", TestPointerEvent);
    const container = screen.getByTestId("pan-zoom-container");
    container.setPointerCapture = () => {};
    fireEvent.pointerDown(container, { pointerId: 1, clientX: 10, clientY: 20 });
    fireEvent.pointerMove(container, { pointerId: 1, clientX: 40, clientY: 35 });

    expect(screen.getByTestId("pan-zoom-content")).toHaveStyle({
      transform: "translate(30px, 15px) scale(1)",
    });
  });

  it("fits the whole sheet in the viewport", () => {
    render(
      <PanZoomContainer>
        <div>Fit Content</div>
      </PanZoomContainer>
    );

    const container = screen.getByTestId("pan-zoom-container");
    const content = screen.getByTestId("pan-zoom-content");
    Object.defineProperty(container, "clientWidth", { configurable: true, value: 200 });
    Object.defineProperty(container, "clientHeight", { configurable: true, value: 100 });
    Object.defineProperty(content, "offsetWidth", { configurable: true, value: 400 });
    Object.defineProperty(content, "offsetHeight", { configurable: true, value: 400 });

    fireEvent.click(screen.getByRole("button", { name: "Full view" }));

    expect(screen.getByTestId("pan-zoom-frame")).toHaveAttribute("data-fullscreen", "true");
    expect(content).toHaveStyle({
      transform: "translate(50px, 0px) scale(0.25)",
    });

    fireEvent.click(screen.getByRole("button", { name: "Exit full view" }));
    expect(screen.getByTestId("pan-zoom-frame")).toHaveAttribute("data-fullscreen", "false");
    expect(content).toHaveStyle({
      transform: "translate(0px, 0px) scale(1)",
    });
  });
});
