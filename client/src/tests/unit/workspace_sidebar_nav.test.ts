import { afterEach, describe, expect, it } from "vitest";

import {
  clearDrawingReturnPath,
  getObjectsSidebarNav,
  getWorkspaceSidebarNav,
  LAST_PROJECT_ID_STORAGE_KEY,
  setDrawingReturnPath,
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";

function clearSidebarNavStorage(): void {
  clearDrawingReturnPath();
  sessionStorage.removeItem(LAST_PROJECT_ID_STORAGE_KEY);
}

describe("getObjectsSidebarNav", () => {
  afterEach(() => {
    clearSidebarNavStorage();
  });

  it("returns the remembered Objects deep link", () => {
    setDrawingReturnPath("2", "8", "15");
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=2&drawingId=8&run=15",
      tooltip: "Return to last viewed drawing",
    });
  });

  it("converts a legacy workspace path to an Objects URL", () => {
    setWorkspaceReturnPath("/projects/2/drawings/8/workspace?run=15");
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=2&drawingId=8&run=15",
      tooltip: "Return to last viewed drawing",
    });
  });

  it("falls back to last project id when no drawing is remembered", () => {
    setLastProjectIdForWorkspaceFallback(7);
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects?projectId=7",
      tooltip: "Objects for your last project",
    });
  });

  it("falls back to bare /objects when nothing is stored", () => {
    expect(getObjectsSidebarNav()).toEqual({
      href: "/objects",
      tooltip: "Drawing viewer and QC/QA objects",
    });
  });
});

describe("getWorkspaceSidebarNav", () => {
  afterEach(() => {
    clearSidebarNavStorage();
  });

  it("returns the remembered Objects URL with drawing viewer tooltip", () => {
    setDrawingReturnPath("2", "8", "15");
    expect(getWorkspaceSidebarNav()).toEqual({
      href: "/objects?projectId=2&drawingId=8&run=15",
      disabled: false,
      tooltip: "Return to drawing viewer",
    });
  });
});
