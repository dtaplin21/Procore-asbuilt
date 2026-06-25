import { describe, expect, it } from "vitest";

import {
  objectsPagePath,
  objectsPagePathForRun,
  parseObjectsRouteParams,
} from "@/lib/objectsRoute";

describe("objectsPagePath", () => {
  it("builds project + drawing links", () => {
    expect(objectsPagePath("2", "8")).toBe("/objects?projectId=2&drawingId=8");
  });

  it("includes run and overlay when provided", () => {
    expect(objectsPagePath("2", "8", "15", "42")).toBe(
      "/objects?projectId=2&drawingId=8&run=15&overlay=42",
    );
  });

  it("omits null run and overlay", () => {
    expect(objectsPagePath("2", "8", null, null)).toBe(
      "/objects?projectId=2&drawingId=8",
    );
  });
});

describe("parseObjectsRouteParams", () => {
  it("reads canonical query param names", () => {
    const params = new URLSearchParams(
      "projectId=2&drawingId=8&run=15&overlay=42",
    );
    expect(parseObjectsRouteParams(params)).toEqual({
      projectId: "2",
      drawingId: "8",
      runId: "15",
      overlayId: "42",
    });
  });
});

describe("objectsPagePathForRun", () => {
  it("includes the run id", () => {
    expect(
      objectsPagePathForRun({
        projectId: "2",
        masterDrawingId: "8",
        runId: "15",
      }),
    ).toBe("/objects?projectId=2&drawingId=8&run=15");
  });
});
