import { describe, expect, it } from "vitest";

import { evidenceFileDownloadUrl } from "@/lib/api/inspections";

describe("inspections API helpers", () => {
  it("builds evidence file download URLs under the project evidence route", () => {
    expect(evidenceFileDownloadUrl("2", "99")).toContain(
      "/api/projects/2/evidence/99/file",
    );
  });
});
