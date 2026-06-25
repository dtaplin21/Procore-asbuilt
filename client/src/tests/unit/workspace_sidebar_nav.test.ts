import { afterEach, describe, expect, it } from "vitest";

import {
  ACTIVE_PROJECT_ID_STORAGE_KEY,
  setActiveProjectIdInStorage,
} from "@/lib/active_project";
import {
  clearDrawingReturnPath,
  clearDrawingReturnPathIfProjectMismatch,
  getDrawingReturnPath,
  getInspectionsSidebarNav,
  getObjectsSidebarNav,
  LAST_PROJECT_ID_STORAGE_KEY,
  setDrawingReturnPath,
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";

function clearSidebarNavStorage(): void {
  clearDrawingReturnPath();
  sessionStorage.removeItem(LAST_PROJECT_ID_STORAGE_KEY);
  sessionStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
}

describe("getInspectionsSidebarNav", () => {
  afterEach(() => {
    clearSidebarNavStorage();
  });

  it("links to bare /inspections when no active project", () => {
    expect(getInspectionsSidebarNav()).toEqual({ href: "/inspections" });
  });

  it("adds optional projectId for bookmarking when active project is stored", () => {
    setActiveProjectIdInStorage(7);
    expect(getInspectionsSidebarNav()).toEqual({
      href: "/inspections?projectId=7",
    });
  });
});

describe("getObjectsSidebarNav", () => {
  afterEach(() => {
    clearSidebarNavStorage();
  });

  it("returns the remembered Objects deep link when it matches active project", () => {
    setActiveProjectIdInStorage(2);
    setDrawingReturnPath("2", "8", "15");
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=2&drawingId=8&run=15",
      tooltip: "Return to last viewed drawing",
    });
  });

  it("ignores return path from a different project", () => {
    setActiveProjectIdInStorage(7);
    setDrawingReturnPath("2", "8", "15");
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=7",
      tooltip: "Objects for active project",
    });
  });

  it("converts a legacy workspace path when project matches", () => {
    setActiveProjectIdInStorage(2);
    setWorkspaceReturnPath("/projects/2/drawings/8/workspace?run=15");
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=2&drawingId=8&run=15",
      tooltip: "Return to last viewed drawing",
    });
  });

  it("falls back to active project id when no drawing is remembered", () => {
    setLastProjectIdForWorkspaceFallback(7);
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=7",
      tooltip: "Objects for active project",
    });
  });

  it("falls back to bare /objects when nothing is stored", () => {
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects",
      tooltip: "Drawing viewer and QC/QA objects",
    });
  });
});

describe("clearDrawingReturnPathIfProjectMismatch", () => {
  afterEach(() => {
    clearSidebarNavStorage();
  });

  it("clears stored return path when project differs", () => {
    setDrawingReturnPath("2", "8", "15");
    clearDrawingReturnPathIfProjectMismatch(7);
    expect(getDrawingReturnPath()).toBeNull();
  });

  it("keeps stored return path when project matches", () => {
    setDrawingReturnPath("2", "8", "15");
    clearDrawingReturnPathIfProjectMismatch(2);
    expect(getDrawingReturnPath()).toBe(
      "/objects?projectId=2&drawingId=8&run=15",
    );
  });
});
