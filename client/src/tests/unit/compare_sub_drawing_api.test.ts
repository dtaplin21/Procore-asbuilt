import { beforeEach, describe, expect, it, vi } from "vitest";
import { compareSubDrawing } from "@/lib/api/drawing_workspace";

describe("compareSubDrawing", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          masterDrawing: { id: 10, projectId: 1, name: "Master" },
          subDrawing: { id: 201, projectId: 1, name: "Sub" },
          alignment: {
            id: 1,
            projectId: 1,
            masterDrawingId: 10,
            subDrawingId: 201,
            subDrawing: { id: 201, name: "Sub" },
          },
          diffs: [],
        }),
      })
    );
  });

  it("POSTs to the compare endpoint with sub_drawing_id in the body", async () => {
    await compareSubDrawing(1, 10, 201);

    expect(fetch).toHaveBeenCalledTimes(1);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toBe("/api/projects/1/drawings/10/compare");
    expect(call[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ sub_drawing_id: 201 }),
      credentials: "include",
    });
  });
});
