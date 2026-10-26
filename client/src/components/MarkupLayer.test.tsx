import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkupLayer } from "./MarkupLayer";
import type { DrawingMarkup } from "../types/drawing_markup";

function setup(props: Partial<React.ComponentProps<typeof MarkupLayer>> = {}) {
  const onCreate = vi.fn();
  const onSelect = vi.fn();
  render(<MarkupLayer markups={[]} tool="polyline" onCreate={onCreate} onSelect={onSelect} {...props} />);
  const layer = screen.getByTestId("markup-layer");
  layer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON() {} }) as DOMRect;
  return { layer, onCreate, onSelect };
}
const fire = (el: Element, type: string, x: number, y: number) =>
  act(() => { el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y })); });
const down = (el: Element, x: number, y: number) => fire(el, "pointerdown", x, y);
const up = (el: Element, x: number, y: number) => fire(el, "pointerup", x, y);

describe("MarkupLayer", () => {
  it("builds a polyline from clicks and finishes on Enter, in fractions", () => {
    const { layer, onCreate } = setup();
    down(layer, 100, 250);
    down(layer, 500, 250);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).toHaveBeenCalledWith("polyline", [[0.1, 0.5], [0.5, 0.5]], null);
  });
  it("does not create a one-point polyline", () => {
    const { layer, onCreate } = setup();
    down(layer, 10, 10);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("does not create a two-point cloud", () => {
    const { layer, onCreate } = setup({ tool: "cloud" });
    down(layer, 10, 10);
    down(layer, 200, 10);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("Escape discards the draft", () => {
    const { layer, onCreate } = setup();
    down(layer, 10, 10);
    down(layer, 300, 10);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("drags a rectangle and ignores a click without a drag", () => {
    const { layer, onCreate } = setup({ tool: "rect" });
    down(layer, 100, 100);
    up(layer, 100, 100);
    expect(onCreate).not.toHaveBeenCalled();
    down(layer, 100, 100);
    up(layer, 300, 200);
    expect(onCreate).toHaveBeenCalledWith("rect", [[0.1, 0.2], [0.3, 0.4]], null);
  });
  it("asks for text and skips an empty answer", () => {
    const ask = vi.fn().mockReturnValueOnce("  Verify slope ").mockReturnValueOnce("   ");
    const { layer, onCreate } = setup({ tool: "text", askLabel: ask });
    down(layer, 500, 250);
    down(layer, 600, 250);
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate).toHaveBeenCalledWith("text", [[0.5, 0.5]], "Verify slope");
  });
  it("selects the markup under the pointer and clears on empty space", () => {
    const line: DrawingMarkup = { id: 7, drawingId: 1, page: 1, kind: "polyline", points: [[0.1, 0.5], [0.9, 0.5]], label: null, inspectionType: "Final", status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "" };
    const { layer, onSelect } = setup({ tool: "select", markups: [line] });
    down(layer, 500, 252);
    expect(onSelect).toHaveBeenLastCalledWith(7);
    down(layer, 500, 50);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
  it("hides types that are not selected and counts untyped as the empty key", () => {
    const base = { drawingId: 1, page: 1, label: null, status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "" };
    const ms: DrawingMarkup[] = [
      { ...base, id: 1, kind: "polyline", points: [[0.1, 0.1], [0.2, 0.2]], inspectionType: "Final" },
      { ...base, id: 2, kind: "polyline", points: [[0.3, 0.3], [0.4, 0.4]], inspectionType: "Flush" },
      { ...base, id: 3, kind: "polyline", points: [[0.5, 0.5], [0.6, 0.6]], inspectionType: null },
    ];
    const { container } = render(<MarkupLayer markups={ms} tool="select" visibleTypes={new Set(["Final", ""])} />);
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
  });
});
