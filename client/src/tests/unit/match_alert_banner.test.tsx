import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchAlertBanner } from "@/components/drawing-workspace/match_alert_banner";

const useInspectionMatchStatusMock = vi.fn();

vi.mock("@/hooks/use_inspection_match_status", () => ({
  useInspectionMatchStatus: (
    evidenceId: string,
    options?: { drawingId?: string; runId?: string | null },
  ) => useInspectionMatchStatusMock(evidenceId, options),
}));

describe("MatchAlertBanner", () => {
  it("renders nothing while loading", () => {
    useInspectionMatchStatusMock.mockReturnValue(null);

    const { container } = render(<MatchAlertBanner evidenceId="357" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when match status is matched", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "357",
      match_status: "matched",
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    });

    const { container } = render(<MatchAlertBanner evidenceId="357" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows index_pending message", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "357",
      match_status: "index_pending",
      bbox: null,
    });

    render(
      <MatchAlertBanner evidenceId="357" drawingId="661" runId="435" />,
    );

    expect(useInspectionMatchStatusMock).toHaveBeenCalledWith("357", {
      drawingId: "661",
      runId: "435",
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Master drawing is still being indexed",
    );
  });

  it("shows needs_review message without confidence numbers", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "357",
      match_status: "needs_review",
      bbox: null,
    });

    render(<MatchAlertBanner evidenceId="357" />);

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(
      "This inspection could not be automatically placed. Please review and confirm the location on the drawing.",
    );
    expect(banner.textContent).not.toMatch(/%/);
    expect(banner.textContent?.toLowerCase()).not.toContain("confidence");
    expect(banner.textContent?.toLowerCase()).not.toContain("score");
  });

  it("shows no_match message", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "357",
      match_status: "no_match",
      bbox: null,
    });

    render(<MatchAlertBanner evidenceId="357" />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No likely location was found on the master drawing for this inspection.",
    );
  });

  it("ucsf needs_review shows alert without numeric scores", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "357",
      match_status: "needs_review",
      bbox: null,
    });

    render(<MatchAlertBanner evidenceId="357" />);

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("could not be automatically placed");
    expect(banner.textContent).not.toMatch(/\d+%/);
  });
});
