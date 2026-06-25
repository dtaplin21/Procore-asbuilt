import { describe, expect, it } from "vitest";

import {
  buildObjectsUrlWithOverlay,
  buildObjectsUrlWithRun,
  buildWorkspaceUrl,
  buildWorkspaceUrlWithFinding,
} from "@/lib/workspace-links";

describe("workspace-links migration aliases", () => {
  it("buildWorkspaceUrl produces Objects URLs", () => {
    expect(buildWorkspaceUrl("2", "8")).toBe("/objects?projectId=2&drawingId=8");
  });

  it("supports legacy object input with run and overlay", () => {
    expect(
      buildWorkspaceUrl({
        projectId: 2,
        masterDrawingId: 8,
        inspectionRunId: 15,
        overlayId: 42,
      }),
    ).toBe("/objects?projectId=2&drawingId=8&run=15&overlay=42");
  });

  it("maps findingId to overlay in Objects URLs", () => {
    expect(buildWorkspaceUrlWithFinding("2", "8", "42")).toBe(
      "/objects?projectId=2&drawingId=8&overlay=42",
    );
  });

  it("buildObjectsUrlWithRun includes run", () => {
    expect(buildObjectsUrlWithRun("2", "8", "15")).toBe(
      "/objects?projectId=2&drawingId=8&run=15",
    );
  });

  it("buildObjectsUrlWithOverlay includes run and overlay", () => {
    expect(buildObjectsUrlWithOverlay("2", "8", "15", "42")).toBe(
      "/objects?projectId=2&drawingId=8&run=15&overlay=42",
    );
  });
});
