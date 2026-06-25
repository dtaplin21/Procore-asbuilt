import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";

import DrawingWorkspacePage from "@/pages/drawing_workspace";

const setLocation = vi.fn();

vi.mock("wouter", () => ({
  useParams: () => ({ projectId: "2", drawingId: "8" }),
  useLocation: () => [
    "/projects/2/drawings/8/workspace?run=15&overlay=42",
    setLocation,
  ],
}));

describe("DrawingWorkspacePage redirect", () => {
  beforeEach(() => {
    setLocation.mockClear();
  });

  it("redirects legacy workspace URLs to Objects", async () => {
    render(<DrawingWorkspacePage />);

    await waitFor(() => {
      expect(setLocation).toHaveBeenCalledWith(
        "/objects?projectId=2&drawingId=8&run=15&overlay=42",
        { replace: true },
      );
    });
  });
});
