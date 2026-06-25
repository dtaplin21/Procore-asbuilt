import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { useCanonicalMasterDrawing } from "@/hooks/use_canonical_master_drawing";

const fetchProjectDashboardSummaryMock = vi.fn();

vi.mock("@/lib/api/projects", () => ({
  fetchProjectDashboardSummary: (...args: unknown[]) =>
    fetchProjectDashboardSummaryMock(...args),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useCanonicalMasterDrawing", () => {
  it("returns canonical id and name from dashboard summary", async () => {
    fetchProjectDashboardSummaryMock.mockResolvedValue({
      project: { id: 2, name: "Site A", masterDrawingId: 10 },
      masterDrawing: { id: 10, name: "Level 1", updated_at: "2026-01-01T00:00:00Z" },
    });

    const { result } = renderHook(() => useCanonicalMasterDrawing(2), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.masterDrawingId).toBe(10);
    expect(result.current.name).toBe("Level 1");
  });

  it("returns null when summary has no canonical master", async () => {
    fetchProjectDashboardSummaryMock.mockResolvedValue({
      project: { id: 2, name: "Site A", masterDrawingId: null },
      masterDrawing: null,
    });

    const { result } = renderHook(() => useCanonicalMasterDrawing(2), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.masterDrawingId).toBeNull();
    expect(result.current.name).toBeNull();
  });
});
