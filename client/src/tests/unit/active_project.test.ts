import { afterEach, describe, expect, it } from "vitest";

import {
  ACTIVE_PROJECT_ID_STORAGE_KEY,
  getActiveProjectIdFromStorage,
  objectsSearchParamsAfterProjectChange,
  parseProjectIdFromLocation,
  replaceDashboardProjectIdInUrl,
  resolveActiveProjectId,
  setActiveProjectIdInStorage,
} from "@/lib/active_project";

describe("parseProjectIdFromLocation", () => {
  it("reads projectId from query string", () => {
    expect(parseProjectIdFromLocation("/objects", "?projectId=7&drawingId=3")).toBe(
      7,
    );
  });

  it("reads projectId from /projects/:id paths", () => {
    expect(parseProjectIdFromLocation("/projects/12/drawings")).toBe(12);
    expect(parseProjectIdFromLocation("/projects/12/drawings/8/workspace")).toBe(
      12,
    );
  });

  it("reads projectId from /workspace/:id stub", () => {
    expect(parseProjectIdFromLocation("/workspace/5")).toBe(5);
  });

  it("returns null when no project id is present", () => {
    expect(parseProjectIdFromLocation("/inspections")).toBeNull();
  });
});

describe("resolveActiveProjectId", () => {
  afterEach(() => {
    sessionStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
  });

  it("prefers URL over session storage", () => {
    setActiveProjectIdInStorage(3);
    expect(resolveActiveProjectId("/objects", "?projectId=9")).toBe(9);
  });

  it("falls back to session storage when URL has no project id", () => {
    setActiveProjectIdInStorage(4);
    expect(resolveActiveProjectId("/")).toBe(4);
  });

  it("returns null when nothing is stored and URL has no project id", () => {
    expect(resolveActiveProjectId("/")).toBeNull();
  });
});

describe("replaceDashboardProjectIdInUrl", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("sets and clears the dashboard projectId query param", () => {
    window.history.replaceState({}, "", "/");
    replaceDashboardProjectIdInUrl("2");
    expect(window.location.search).toBe("?projectId=2");

    replaceDashboardProjectIdInUrl(null);
    expect(window.location.search).toBe("");
  });
});

describe("objectsSearchParamsAfterProjectChange", () => {
  it("sets projectId and strips cross-project deep-link params", () => {
    const current = new URLSearchParams(
      "projectId=2&drawingId=8&run=15&overlay=42",
    );
    const next = objectsSearchParamsAfterProjectChange(current, 7);
    expect(next.get("projectId")).toBe("7");
    expect(next.has("drawingId")).toBe(false);
    expect(next.has("run")).toBe(false);
    expect(next.has("overlay")).toBe(false);
  });
});

describe("getActiveProjectIdFromStorage", () => {
  afterEach(() => {
    sessionStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
  });

  it("round-trips through setActiveProjectIdInStorage", () => {
    setActiveProjectIdInStorage(11);
    expect(getActiveProjectIdFromStorage()).toBe(11);
    setActiveProjectIdInStorage(null);
    expect(getActiveProjectIdFromStorage()).toBeNull();
  });
});

describe("setLastProjectIdForWorkspaceFallback", () => {
  afterEach(() => {
    sessionStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
    sessionStorage.removeItem("qcqa:lastProjectId");
  });

  it("writes both active project and legacy fallback keys", async () => {
    const { setLastProjectIdForWorkspaceFallback } = await import(
      "@/lib/workspace-return-path"
    );
    setLastProjectIdForWorkspaceFallback(5);
    expect(getActiveProjectIdFromStorage()).toBe(5);
    expect(sessionStorage.getItem("qcqa:lastProjectId")).toBe("5");
  });
});
