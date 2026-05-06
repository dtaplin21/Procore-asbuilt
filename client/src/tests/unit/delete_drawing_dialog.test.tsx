import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DeleteDrawingDialog } from "@/components/drawings/DeleteDrawingDialog";

const mocks = vi.hoisted(() => ({
  fetchDrawingDeleteSummary: vi.fn(),
  deleteProjectDrawing: vi.fn(),
}));

vi.mock("@/lib/api/projects", () => ({
  fetchDrawingDeleteSummary: mocks.fetchDrawingDeleteSummary,
  deleteProjectDrawing: mocks.deleteProjectDrawing,
}));

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const summaryBody = {
  alignmentsCount: 0,
  diffsCount: 0,
  regionsCount: 0,
  overlaysCount: 0,
  findingsWithDrawingCount: 0,
  evidenceLinksCount: 0,
  isCanonicalMaster: false,
  masterDrawingId: 101,
};

describe("DeleteDrawingDialog", () => {
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
    mocks.fetchDrawingDeleteSummary.mockResolvedValue(summaryBody);
    mocks.deleteProjectDrawing.mockResolvedValue(undefined);
  });

  it("loads delete summary and sends DELETE after typing the drawing name", async () => {
    const onOpenChange = vi.fn();
    const onDeleteSuccess = vi.fn();

    renderWithQuery(
      <DeleteDrawingDialog
        projectId={2}
        drawing={{ id: 101, name: "Floor-1.pdf" }}
        open
        onOpenChange={onOpenChange}
        onDeleteSuccess={onDeleteSuccess}
      />
    );

    await waitFor(() =>
      expect(mocks.fetchDrawingDeleteSummary).toHaveBeenCalledWith(2, 101)
    );

    const deleteBtn = screen.getByTestId("delete-drawing-confirm");
    expect(deleteBtn).toBeDisabled();

    fireEvent.change(screen.getByTestId("delete-drawing-confirm-name"), {
      target: { value: "Floor-1.pdf" },
    });
    expect(deleteBtn).not.toBeDisabled();

    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mocks.deleteProjectDrawing).toHaveBeenCalledWith(2, 101);
      expect(onDeleteSuccess).toHaveBeenCalledWith(101);
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps Delete disabled when confirmation name does not match", async () => {
    renderWithQuery(
      <DeleteDrawingDialog
        projectId={1}
        drawing={{ id: 55, name: "A.pdf" }}
        open
        onOpenChange={vi.fn()}
      />
    );

    await waitFor(() =>
      expect(mocks.fetchDrawingDeleteSummary).toHaveBeenCalled()
    );

    fireEvent.change(screen.getByTestId("delete-drawing-confirm-name"), {
      target: { value: "B.pdf" },
    });
    expect(screen.getByTestId("delete-drawing-confirm")).toBeDisabled();
    expect(mocks.deleteProjectDrawing).not.toHaveBeenCalled();
  });
});
