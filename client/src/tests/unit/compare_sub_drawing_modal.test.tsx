import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import CompareSubDrawingModal from "@/components/drawing-workspace/compare_sub_drawing_modal";
import { useProjectDrawings } from "@/hooks/use_project_drawings";

vi.mock("@/hooks/use_project_drawings", () => ({
  useProjectDrawings: vi.fn(),
}));

const mockUseProjectDrawings = vi.mocked(useProjectDrawings);

describe("CompareSubDrawingModal", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseProjectDrawings.mockReturnValue({
      drawings: [
        { id: 201, projectId: 1, name: "Candidate drawing", source: "upload" },
      ],
      loading: false,
      error: null,
      reload: vi.fn().mockResolvedValue(undefined),
    });
  });

  it("shows sub drawings, selects one, and calls onConfirmCompare with Compare", () => {
    const onConfirmCompare = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <CompareSubDrawingModal
        isOpen
        projectId={1}
        masterDrawingId={10}
        onClose={onClose}
        onConfirmCompare={onConfirmCompare}
        compareLoading={false}
        compareError={null}
      />
    );

    fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));

    expect(onConfirmCompare).toHaveBeenCalledWith(201);
  });

  it("shows Comparing... on the confirm button while compareLoading is true", () => {
    render(
      <CompareSubDrawingModal
        isOpen
        projectId={1}
        masterDrawingId={10}
        onClose={vi.fn()}
        onConfirmCompare={vi.fn()}
        compareLoading
        compareError={null}
      />
    );

    const btn = screen.getByTestId("confirm-compare-sub-drawing-button");
    expect(btn).toHaveTextContent("Comparing...");
    expect(btn).toBeDisabled();
  });

  it("renders compare error message for retry", () => {
    const onConfirmCompare = vi.fn().mockResolvedValue(undefined);

    render(
      <CompareSubDrawingModal
        isOpen
        projectId={1}
        masterDrawingId={10}
        onClose={vi.fn()}
        onConfirmCompare={onConfirmCompare}
        compareLoading={false}
        compareError="Compare failed on server"
      />
    );

    expect(screen.getByText("Compare failed")).toBeInTheDocument();
    expect(screen.getByText("Compare failed on server")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("sub-drawing-item-201"));
    fireEvent.click(screen.getByTestId("confirm-compare-sub-drawing-button"));
    expect(onConfirmCompare).toHaveBeenCalledWith(201);
  });

  it("disables escape and backdrop close while compareLoading", () => {
    const onClose = vi.fn();

    render(
      <CompareSubDrawingModal
        isOpen
        projectId={1}
        masterDrawingId={10}
        onClose={onClose}
        onConfirmCompare={vi.fn()}
        compareLoading
        compareError={null}
      />
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("compare-sub-drawing-modal-backdrop"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
