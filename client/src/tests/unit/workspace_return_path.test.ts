import { afterEach, describe, expect, it } from "vitest";

import {
  clearDrawingReturnPath,
  getDrawingReturnPath,
  setDrawingReturnPath,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";

describe("workspace return path", () => {
  afterEach(() => {
    clearDrawingReturnPath();
  });

  it("stores Objects URLs in sessionStorage", () => {
    setDrawingReturnPath("2", "8", "15");
    expect(getDrawingReturnPath()).toBe("/objects?projectId=2&drawingId=8&run=15");
  });

  it("setWorkspaceReturnPath stores full paths including overlay", () => {
    setWorkspaceReturnPath("/objects?projectId=2&drawingId=8&run=15&overlay=42");
    expect(getDrawingReturnPath()).toBe(
      "/objects?projectId=2&drawingId=8&run=15&overlay=42",
    );
  });

  it("clears the stored path", () => {
    setDrawingReturnPath("2", "8");
    clearDrawingReturnPath();
    expect(getDrawingReturnPath()).toBeNull();
  });
});
