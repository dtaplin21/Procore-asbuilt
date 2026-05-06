/**
 * Drawing picker: when summary includes a canonical master, redirect to workspace.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DashboardSummaryResponse } from "@shared/schema";

import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import { getQueryFn } from "@/lib/queryClient";
import DrawingPickerPage from "@/pages/drawing_picker";

const setLocation = vi.fn();

vi.mock("@/lib/api/projects", () => ({
  fetchProjectDashboardSummary: vi.fn(),
}));

vi.mock("wouter", async (importOriginal) => {
  const mod = await importOriginal<typeof import("wouter")>();
  return {
    ...mod,
    useLocation: () => ["/projects/7/drawings", setLocation] as const,
    useParams: () => ({ projectId: "7" }),
  };
});

const mockFetchSummary = vi.mocked(fetchProjectDashboardSummary);

function makeSummary(masterDrawingId: number | null | undefined): DashboardSummaryResponse {
  return {
    project: {
      id: 7,
      name: "Test project",
      company_id: 1,
      masterDrawingId: masterDrawingId ?? null,
    },
    company_context: {
      project_company_id: 1,
      matches_active_company: true,
    },
    sync_health: {
      connected: false,
      sync_status: "idle",
    },
    kpis: {
      total_findings: 0,
      open_findings: 0,
      drawings_count: 0,
      evidence_count: 0,
      inspections_count: 0,
    },
  };
}

function renderPicker() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        queryFn: getQueryFn({ on401: "throw" }),
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DrawingPickerPage />
    </QueryClientProvider>
  );
}

describe("DrawingPickerPage — canonical master redirect", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls setLocation with workspace URL when API returns masterDrawingId", async () => {
    mockFetchSummary.mockResolvedValue(makeSummary(42));
    renderPicker();

    await waitFor(() => {
      expect(setLocation).toHaveBeenCalledWith("/projects/7/drawings/42/workspace");
    });
  });

  it("does not redirect when masterDrawingId is absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/api/projects/7/drawings") && !url.includes("dashboard")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        throw new Error(`Unmocked fetch: ${url}`);
      })
    );

    mockFetchSummary.mockResolvedValue(makeSummary(null));
    renderPicker();

    await waitFor(() => {
      expect(mockFetchSummary).toHaveBeenCalled();
    });
    expect(setLocation).not.toHaveBeenCalled();
  });
});
