import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";

import {
  useDrawingRegions,
  useRegionInspectionSummary,
} from "@/hooks/use-drawing-regions";

const fetchDrawingRegionsMock = vi.fn();
const fetchRegionInspectionSummaryMock = vi.fn();

vi.mock("@/lib/api/drawing_regions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/drawing_regions")>();
  return {
    ...actual,
    fetchDrawingRegions: (...args: unknown[]) => fetchDrawingRegionsMock(...args),
    fetchRegionInspectionSummary: (...args: unknown[]) =>
      fetchRegionInspectionSummaryMock(...args),
  };
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("use-drawing-regions hooks", () => {
  beforeEach(() => {
    fetchDrawingRegionsMock.mockReset();
    fetchRegionInspectionSummaryMock.mockReset();
  });

  it("loads drawing regions for a project + master drawing scope", async () => {
    fetchDrawingRegionsMock.mockResolvedValue([
      { id: 1, master_drawing_id: 42, label: "Zone A" },
    ]);

    const { result } = renderHook(
      () => useDrawingRegions({ projectId: 3, masterDrawingId: 42 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(fetchDrawingRegionsMock).toHaveBeenCalledWith({
      projectId: 3,
      masterDrawingId: 42,
    });
    expect(result.current.data).toHaveLength(1);
  });

  it("returns summary items from the wrapped API response", async () => {
    fetchRegionInspectionSummaryMock.mockResolvedValue({
      items: [{ regionId: 7, masterDrawingId: 42, state: "hidden", label: "Roof" }],
    });

    const { result } = renderHook(
      () => useRegionInspectionSummary({ projectId: 3, masterDrawingId: 42 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.[0]?.regionId).toBe(7);
  });

  it("does not fetch when scope ids are missing", () => {
    renderHook(() => useDrawingRegions({ projectId: null, masterDrawingId: 42 }), {
      wrapper,
    });

    expect(fetchDrawingRegionsMock).not.toHaveBeenCalled();
  });
});
