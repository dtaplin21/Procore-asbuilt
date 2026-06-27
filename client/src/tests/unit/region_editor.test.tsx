import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { RegionEditor } from "@/components/drawing-workspace/region_editor";

const fetchDrawingRegionsMock = vi.fn();
const createDrawingRegionMock = vi.fn();
const deleteDrawingRegionMock = vi.fn();

vi.mock("@/lib/api/drawing_regions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/drawing_regions")>();
  return {
    ...actual,
    fetchDrawingRegions: (...args: unknown[]) => fetchDrawingRegionsMock(...args),
    createDrawingRegion: (...args: unknown[]) => createDrawingRegionMock(...args),
    deleteDrawingRegion: (...args: unknown[]) => deleteDrawingRegionMock(...args),
  };
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

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

describe("RegionEditor", () => {
  beforeEach(() => {
    fetchDrawingRegionsMock.mockReset();
    createDrawingRegionMock.mockReset();
    deleteDrawingRegionMock.mockReset();
    fetchDrawingRegionsMock.mockResolvedValue([
      {
        id: 9,
        master_drawing_id: 42,
        label: "Utility MR",
        page: 1,
        geometry: { type: "rect", x: 0.1, y: 0.1, width: 0.1, height: 0.1 },
        inspection_type_tags: ["Rough In"],
        location_tags: ["Utility MR"],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    createDrawingRegionMock.mockResolvedValue({ id: 10 });
    deleteDrawingRegionMock.mockResolvedValue(undefined);
  });

  it("lists existing regions and deletes one", async () => {
    render(
      <RegionEditor
        projectId={3}
        masterDrawingId={42}
        imageUrl="/drawing.png"
        pageWidth={1000}
        pageHeight={800}
      />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.getByText(/Utility MR/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("region-editor-delete-9"));

    await waitFor(() => {
      expect(deleteDrawingRegionMock).toHaveBeenCalledWith({
        projectId: 3,
        masterDrawingId: 42,
        regionId: 9,
      });
    });
  });

  it("creates a region after draw + tag form submit", async () => {
    render(
      <RegionEditor
        projectId={3}
        masterDrawingId={42}
        imageUrl="/drawing.png"
        pageWidth={1000}
        pageHeight={800}
      />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.getByTestId("region-draw-surface")).toBeInTheDocument();
    });

    const surface = screen.getByTestId("region-draw-surface");
    mockRect(surface, 500, 400);

    fireEvent.mouseDown(surface, { clientX: 50, clientY: 40 });
    fireEvent.mouseMove(surface, { clientX: 250, clientY: 200 });
    fireEvent.mouseUp(surface);

    fireEvent.change(screen.getByTestId("region-label-input"), {
      target: { value: "New Zone" },
    });
    fireEvent.change(screen.getByTestId("region-inspection-types-input"), {
      target: { value: "Final" },
    });
    fireEvent.change(screen.getByTestId("region-locations-input"), {
      target: { value: "Roof" },
    });
    fireEvent.click(screen.getByTestId("region-tag-form-save"));

    await waitFor(() => {
      expect(createDrawingRegionMock).toHaveBeenCalledWith({
        projectId: 3,
        masterDrawingId: 42,
        body: {
          label: "New Zone",
          geometry: {
            type: "rect",
            x: 0.1,
            y: 0.1,
            width: 0.4,
            height: 0.4,
          },
          inspection_type_tags: ["Final"],
          location_tags: ["Roof"],
        },
      });
    });
  });
});
