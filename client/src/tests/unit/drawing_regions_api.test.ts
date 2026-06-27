/**
 * client/src/tests/unit/drawing_regions_api.test.ts
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  buildRegionInspectionSummaryUrl,
  createDrawingRegion,
  deleteDrawingRegion,
  drawingRegionsQueryKey,
  fetchRegionInspectionSummary,
  listDrawingRegions,
  regionInspectionSummaryQueryKey,
  updateDrawingRegion,
} from "@/lib/api/drawing_regions";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const PROJECT_ID = 2;
const MASTER_DRAWING_ID = 42;

const WIRE_REGION = {
  id: 7,
  master_drawing_id: MASTER_DRAWING_ID,
  label: "Roof",
  page: 1,
  geometry: { type: "rect", x: 0.01, y: 0.02, width: 0.05, height: 0.06 },
  polygon_points: null,
  inspection_type_tags: ["Final"],
  location_tags: ["Roof"],
  created_at: "2026-06-24T00:00:00Z",
  updated_at: "2026-06-24T00:00:00Z",
};

describe("drawing_regions API helpers", () => {
  it("builds project-scoped region URLs", () => {
    expect(buildRegionInspectionSummaryUrl(PROJECT_ID, MASTER_DRAWING_ID)).toBe(
      "/api/projects/2/drawings/42/region-inspection-summary",
    );
  });

  it("builds stable react-query keys", () => {
    expect(drawingRegionsQueryKey(PROJECT_ID, MASTER_DRAWING_ID)).toEqual([
      "drawing-regions",
      "2",
      "42",
    ]);
    expect(regionInspectionSummaryQueryKey("2", "42")).toEqual([
      "region-inspection-summary",
      "2",
      "42",
    ]);
  });
});

describe("drawing_regions API client", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listDrawingRegions hits the project-scoped regions route", async () => {
    fetchMock.mockReturnValue(jsonResponse([WIRE_REGION]));
    const regions = await listDrawingRegions({
      projectId: PROJECT_ID,
      masterDrawingId: MASTER_DRAWING_ID,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/2/drawings/42/regions",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(regions).toHaveLength(1);
    expect(regions[0]).toEqual(WIRE_REGION);
  });

  it("createDrawingRegion POSTs normalized geometry and tags", async () => {
    fetchMock.mockReturnValue(jsonResponse(WIRE_REGION, 201));

    await createDrawingRegion({
      projectId: PROJECT_ID,
      masterDrawingId: MASTER_DRAWING_ID,
      body: {
        label: "Roof",
        geometry: { type: "rect", x: 0.01, y: 0.02, width: 0.05, height: 0.06 },
        polygon_points: [
          [0.01, 0.02],
          [0.06, 0.02],
          [0.04, 0.08],
        ],
        inspection_type_tags: ["Final"],
        location_tags: ["Roof"],
      },
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects/2/drawings/42/regions");
    expect(init.method).toBe("POST");
    expect(init.headers.get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(init.body)).toEqual({
      label: "Roof",
      geometry: { type: "rect", x: 0.01, y: 0.02, width: 0.05, height: 0.06 },
      polygon_points: [
        [0.01, 0.02],
        [0.06, 0.02],
        [0.04, 0.08],
      ],
      inspection_type_tags: ["Final"],
      location_tags: ["Roof"],
    });
  });

  it("updateDrawingRegion PATCHes only provided fields", async () => {
    fetchMock.mockReturnValue(jsonResponse(WIRE_REGION));

    await updateDrawingRegion({
      projectId: PROJECT_ID,
      masterDrawingId: MASTER_DRAWING_ID,
      regionId: 7,
      body: {
        inspection_type_tags: ["Flush"],
        location_tags: [],
      },
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects/2/drawings/42/regions/7");
    expect(init.method).toBe("PATCH");
    const sentBody = JSON.parse(init.body);
    expect(sentBody).toEqual({
      inspection_type_tags: ["Flush"],
      location_tags: [],
    });
    expect(sentBody.geometry).toBeUndefined();
  });

  it("deleteDrawingRegion succeeds on 204 with no body", async () => {
    fetchMock.mockReturnValue(Promise.resolve(new Response(null, { status: 204 })));
    await expect(
      deleteDrawingRegion({
        projectId: PROJECT_ID,
        masterDrawingId: MASTER_DRAWING_ID,
        regionId: 7,
      }),
    ).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/2/drawings/42/regions/7");
  });

  it("deleteDrawingRegion throws on failure", async () => {
    fetchMock.mockReturnValue(jsonResponse({ detail: "not found" }, 404));
    await expect(
      deleteDrawingRegion({
        projectId: PROJECT_ID,
        masterDrawingId: MASTER_DRAWING_ID,
        regionId: 999,
      }),
    ).rejects.toThrow(/not found|404/i);
  });

  it("fetchRegionInspectionSummary returns camelCase summary items", async () => {
    fetchMock.mockReturnValue(
      jsonResponse({
        items: [
          {
            regionId: 7,
            masterDrawingId: MASTER_DRAWING_ID,
            state: "inspected",
            label: "Roof",
            bbox: [0.1, 0.1, 0.2, 0.2],
            locationTags: ["Roof"],
            inspectionTypeTags: ["Final"],
            latestOverlayId: 11,
            latestInspectionRunId: 15,
            inspectionStatusDisplay: "Approved As Noted",
            inspectionDate: "2026-06-24",
            procoreInspectionId: null,
          },
        ],
      }),
    );

    const summary = await fetchRegionInspectionSummary({
      projectId: PROJECT_ID,
      masterDrawingId: MASTER_DRAWING_ID,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/2/drawings/42/region-inspection-summary",
    );
    expect(summary.items[0]).toEqual({
      regionId: 7,
      masterDrawingId: MASTER_DRAWING_ID,
      state: "inspected",
      label: "Roof",
      bbox: [0.1, 0.1, 0.2, 0.2],
      locationTags: ["Roof"],
      inspectionTypeTags: ["Final"],
      latestOverlayId: 11,
      latestInspectionRunId: 15,
      inspectionStatusDisplay: "Approved As Noted",
      inspectionDate: "2026-06-24",
      procoreInspectionId: null,
    });
  });
});
