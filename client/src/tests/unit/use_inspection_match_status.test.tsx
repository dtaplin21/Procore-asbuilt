import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  fetchInspectionMatchStatus,
  useInspectionMatchStatus,
} from "@/hooks/use_inspection_match_status";

const fetchMock = vi.fn();

vi.mock("@/lib/api/http", () => ({
  resolveFetchUrl: (url: string) => url,
}));

describe("useInspectionMatchStatus", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("returns null while loading", () => {
    fetchMock.mockReturnValue(new Promise(() => undefined));

    const { result } = renderHook(() => useInspectionMatchStatus("inspection-123"));

    expect(result.current).toBeNull();
  });

  it("returns match status from the API", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        inspection_id: "inspection-123",
        match_status: "matched",
        bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
      }),
    });

    const { result } = renderHook(() => useInspectionMatchStatus("inspection-123"));

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current).toEqual({
      inspection_id: "inspection-123",
      match_status: "matched",
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    });
  });

  it("falls back to needs_review when the request fails", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useInspectionMatchStatus("inspection-123"));

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current).toEqual({
      inspection_id: "inspection-123",
      match_status: "needs_review",
      bbox: null,
    });
  });
});

describe("fetchInspectionMatchStatus", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("throws when the API returns a non-ok response", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({}),
    });

    await expect(fetchInspectionMatchStatus("inspection-123")).rejects.toThrow(
      "Failed to fetch inspection match status",
    );
  });
});
