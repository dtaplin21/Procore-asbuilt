import { describe, expect, it } from "vitest";

import type { MasterDrawing } from "@/lib/api/drawings";

describe("drawings API types", () => {
  it("MasterDrawing uses camelCase viewer fields", () => {
    const drawing: MasterDrawing = {
      id: "10",
      projectId: "2",
      name: "Master.pdf",
      imageUrl: "/api/projects/2/drawings/10/pages/1/image",
    };
    expect(drawing.imageUrl).toContain("/pages/1/image");
  });
});
