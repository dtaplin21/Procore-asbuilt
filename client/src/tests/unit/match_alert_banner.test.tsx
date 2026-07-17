import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchAlertBanner } from "@/components/drawing-workspace/match_alert_banner";

const useInspectionMatchStatusMock = vi.fn();

vi.mock("@/hooks/use_inspection_match_status", () => ({
  useInspectionMatchStatus: (inspectionId: string) =>
    useInspectionMatchStatusMock(inspectionId),
}));

describe("MatchAlertBanner", () => {
  it("renders nothing while loading", () => {
    useInspectionMatchStatusMock.mockReturnValue(null);

    const { container } = render(<MatchAlertBanner inspectionId="inspection-123" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when match status is matched", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "inspection-123",
      match_status: "matched",
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    });

    const { container } = render(<MatchAlertBanner inspectionId="inspection-123" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows needs_review message without confidence numbers", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "test",
      match_status: "needs_review",
      bbox: null,
    });

    render(<MatchAlertBanner inspectionId="test" />);

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
      inspection_id: "test",
      match_status: "no_match",
      bbox: null,
    });

    render(<MatchAlertBanner inspectionId="test" />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No likely location was found on the master drawing for this inspection.",
    );
  });

  it("ucsf needs_review shows alert without numeric scores", () => {
    useInspectionMatchStatusMock.mockReturnValue({
      inspection_id: "ucsf-evidence-1",
      match_status: "needs_review",
      bbox: null,
    });

    render(<MatchAlertBanner inspectionId="ucsf-evidence-1" />);

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("could not be automatically placed");
    expect(banner.textContent).not.toMatch(/\d+%/);
  });
});
