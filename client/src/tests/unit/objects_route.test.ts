import { describe, expect, it } from "vitest";

import {
  objectsPagePath,
  objectsPagePathForRun,
  objectsPagePathWithParams,
  parseObjectsRouteParams,
  workspacePathToObjectsUrl,
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
      "projectId=2&drawingId=8&run=15&overlay=42&region=7",
    );
    expect(parseObjectsRouteParams(params)).toEqual({
      projectId: "2",
      drawingId: "8",
      runId: "15",
      overlayId: "42",
      regionId: "7",
    });
  });
});

describe("objectsPagePathWithParams", () => {
  it("includes optional run, overlay, and region", () => {
    expect(
      objectsPagePathWithParams({
        projectId: "2",
        drawingId: "8",
        runId: "15",
        overlayId: "42",
        regionId: "7",
      }),
    ).toBe("/objects?projectId=2&drawingId=8&run=15&overlay=42&region=7");
  });
});

describe("workspacePathToObjectsUrl", () => {
  it("maps legacy workspace paths to Objects URLs", () => {
    expect(
      workspacePathToObjectsUrl("/projects/2/drawings/8/workspace"),
    ).toBe("/objects?projectId=2&drawingId=8");
  });

  it("preserves run and overlay query params", () => {
    expect(
      workspacePathToObjectsUrl(
        "/projects/2/drawings/8/workspace",
        "?run=15&overlay=42",
      ),
    ).toBe("/objects?projectId=2&drawingId=8&run=15&overlay=42");
  });

  it("maps legacy findingId to overlay", () => {
    expect(
      workspacePathToObjectsUrl(
        "/projects/2/drawings/8/workspace",
        "?findingId=99",
      ),
    ).toBe("/objects?projectId=2&drawingId=8&overlay=99");
  });

  it("returns null for non-workspace paths", () => {
    expect(workspacePathToObjectsUrl("/objects")).toBeNull();
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
