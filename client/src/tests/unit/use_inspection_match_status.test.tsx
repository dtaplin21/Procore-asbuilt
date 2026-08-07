import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  MATCH_STATUS_MAX_POLL_ATTEMPTS,
  MATCH_STATUS_POLL_INTERVAL_MS,
  fetchInspectionMatchStatus,
  isTerminalMatchStatus,
  useInspectionMatchStatus,
} from "@/hooks/use_inspection_match_status";

const fetchMock = vi.fn();
const invalidateOverlaysForRunMock = vi.fn();

vi.mock("@/lib/api/http", () => ({
  resolveFetchUrl: (url: string) => url,
}));

vi.mock("@/lib/api/overlays", () => ({
  invalidateOverlaysForRun: (...args: unknown[]) =>
    invalidateOverlaysForRunMock(...args),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("isTerminalMatchStatus", () => {
  it("treats matched, needs_review, and no_match as terminal", () => {
    expect(isTerminalMatchStatus("matched")).toBe(true);
    expect(isTerminalMatchStatus("needs_review")).toBe(true);
    expect(isTerminalMatchStatus("no_match")).toBe(true);
    expect(isTerminalMatchStatus("index_pending")).toBe(false);
  });
});

describe("useInspectionMatchStatus", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    invalidateOverlaysForRunMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("returns null while loading", () => {
    fetchMock.mockReturnValue(new Promise(() => undefined));

    const { result } = renderHook(() => useInspectionMatchStatus("357"), {
      wrapper: createWrapper(),
    });

    expect(result.current).toBeNull();
  });

  it("returns match status from the API", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        inspection_id: "357",
        match_status: "matched",
        bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
      }),
    });

    const { result } = renderHook(() => useInspectionMatchStatus("357"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current).toEqual({
      inspection_id: "357",
      match_status: "matched",
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("polls until match status is terminal", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          inspection_id: "357",
          match_status: "index_pending",
          bbox: null,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          inspection_id: "357",
          match_status: "matched",
          bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
        }),
      });

    const { result } = renderHook(
      () =>
        useInspectionMatchStatus("357", {
          drawingId: "661",
          runId: "435",
        }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current?.match_status).toBe("index_pending");
    });

    await vi.advanceTimersByTimeAsync(MATCH_STATUS_POLL_INTERVAL_MS);

    await waitFor(() => {
      expect(result.current?.match_status).toBe("matched");
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(invalidateOverlaysForRunMock).toHaveBeenCalledWith(
      expect.anything(),
      "661",
      "435",
    );

    vi.useRealTimers();
  });

  it("stops polling after the max attempt count", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        inspection_id: "357",
        match_status: "index_pending",
        bbox: null,
      }),
    });

    renderHook(() => useInspectionMatchStatus("357"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    for (let attempt = 1; attempt < MATCH_STATUS_MAX_POLL_ATTEMPTS; attempt += 1) {
      await vi.advanceTimersByTimeAsync(MATCH_STATUS_POLL_INTERVAL_MS);
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledTimes(attempt + 1);
      });
    }

    await vi.advanceTimersByTimeAsync(MATCH_STATUS_POLL_INTERVAL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(MATCH_STATUS_MAX_POLL_ATTEMPTS);

    vi.useRealTimers();
  });

  it("falls back to needs_review when the request fails", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useInspectionMatchStatus("357"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current).toEqual({
      inspection_id: "357",
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

    await expect(fetchInspectionMatchStatus("357")).rejects.toThrow(
      "Failed to fetch inspection match status",
    );
  });
});
