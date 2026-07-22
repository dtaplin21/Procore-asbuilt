import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteInspectionRun } from "@/lib/api/inspections";

describe("deleteInspectionRun", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true }),
      }),
    );
  });

  it("calls DELETE on the inspection run URL with credentials", async () => {
    await deleteInspectionRun("2", "327");

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toMatch(/\/api\/projects\/2\/inspections\/runs\/327$/);
    expect(init).toMatchObject({
      method: "DELETE",
      credentials: "include",
    });
  });
});
