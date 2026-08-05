import { describe, expect, it } from "vitest";

import {
  formatDrawingIndexSummary,
  isDrawingIndexInProgress,
} from "@/lib/drawing-index/format_index_summary";

describe("formatDrawingIndexSummary", () => {
  it("returns null while indexing is in progress", () => {
    expect(
      formatDrawingIndexSummary({
        status: "processing",
        stats: null,
        scale: null,
        error: null,
        indexed_at: null,
      }),
    ).toBeNull();
  });

  it("formats ready index stats for the drawing header", () => {
    expect(
      formatDrawingIndexSummary({
        status: "ready",
        stats: { pages: 3, regions: 842, text_elements: 1200, scale_found: true },
        scale: { raw_text: '1" = 10\'' },
        error: null,
        indexed_at: "2026-01-01T00:00:00Z",
      }),
    ).toBe('842 regions indexed · Scale 1" = 10\' · 3 pages');
  });
});

describe("isDrawingIndexInProgress", () => {
  it("treats pending and processing as in progress", () => {
    expect(isDrawingIndexInProgress("pending")).toBe(true);
    expect(isDrawingIndexInProgress("processing")).toBe(true);
    expect(isDrawingIndexInProgress("ready")).toBe(false);
  });
});
