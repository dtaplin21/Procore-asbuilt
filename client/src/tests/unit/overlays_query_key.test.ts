import { describe, expect, it } from "vitest";

import { overlaysQueryKey } from "@/lib/api/overlays";

describe("overlaysQueryKey", () => {
  it("uses latest sentinel when runId is omitted", () => {
    expect(overlaysQueryKey("8")).toEqual(["drawing-overlays", "8", "latest"]);
  });

  it("includes a specific run id in the cache key", () => {
    expect(overlaysQueryKey("8", "15")).toEqual(["drawing-overlays", "8", "15"]);
  });

  it("treats null runId as latest", () => {
    expect(overlaysQueryKey("8", null)).toEqual(["drawing-overlays", "8", "latest"]);
  });
});
