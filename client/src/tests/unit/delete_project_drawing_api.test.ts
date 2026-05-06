import { beforeEach, describe, expect, it, vi } from "vitest";
import { deleteProjectDrawing } from "@/lib/api/projects";

describe("deleteProjectDrawing", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
      })
    );
  });

  it("calls DELETE on the project drawing URL with credentials", async () => {
    await deleteProjectDrawing(3, 9001);

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toMatch(/\/api\/projects\/3\/drawings\/9001$/);
    expect(init).toMatchObject({
      method: "DELETE",
      credentials: "include",
    });
  });
});
