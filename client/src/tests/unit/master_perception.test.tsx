import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PerceptionSheet } from "@/components/testing/perception_sheet";
import { DEFAULT_LAYERS, type MasterPerception } from "@/lib/testing/perception_model";

const perception: MasterPerception = {
  master: {
    id: "1722",
    drawingNumber: "Master.pdf",
    page: 1,
    imageUrl: "/api/projects/1348/drawings/1722/pages/1/image",
    widthPx: 1000,
    heightPx: 1000,
    projectId: 1348,
  },
  ocr: [
    {
      id: "1",
      text: "10+05.00",
      bbox: { x: 100, y: 200, width: 80, height: 16 },
      confidence: 0.4,
      isStationLabel: true,
      stationLabel: "10+05.00",
      parsedStation: 1005,
    },
    {
      id: "2",
      text: "Rough In",
      bbox: { x: 300, y: 200, width: 70, height: 16 },
      confidence: 0.9,
      category: "inspection_type",
      isStationLabel: false,
    },
  ],
  ssmh: [],
  pipes: [
    {
      id: "approx",
      polyline: [
        { x: 10, y: 10 },
        { x: 40, y: 10 },
      ],
      source: "survey_chain_fallback",
    },
  ],
  edges: null,
  contours: [],
  controlPoints: [],
  registration: {
    evidenceRunId: "",
    transform: null,
    rmsResidualPx: null,
    pointCount: 1,
    collinearityScore: 1,
    quality: "fail",
  },
  regions: [],
  overlays: [],
  warnings: [],
};

describe("pipeline redraw", () => {
  it("draws the stored station text and dashes the survey-chain pipe", () => {
    const { container } = render(
      <PerceptionSheet
        perception={perception}
        layers={{ ...DEFAULT_LAYERS, pipes: true }}
        minConfidence={0}
        showImage={false}
        imageUrl=""
        diff={false}
        crosshair={null}
        onHover={() => undefined}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getByTestId("perception-redraw")).toBeInTheDocument();
    expect(screen.getByText("10+05.00 (1005)")).toBeInTheDocument();
    const approx = container.querySelector('[data-testid="pipes-approx"] polyline');
    expect(approx?.getAttribute("stroke-dasharray")).toBe("6 4");
  });

  it("hides OCR when that layer is off and the box is not a station or vocabulary hit", () => {
    render(
      <PerceptionSheet
        perception={{
          ...perception,
          ocr: [
            {
              id: "9",
              text: "NOTE",
              bbox: { x: 1, y: 1, width: 10, height: 10 },
              confidence: 1,
              isStationLabel: false,
            },
          ],
        }}
        layers={{ ...DEFAULT_LAYERS, ocr: false, stations: false, vocabulary: false }}
        minConfidence={0}
        showImage={false}
        imageUrl=""
        diff={false}
        crosshair={null}
        onHover={() => undefined}
        onSelect={() => undefined}
      />,
    );
    expect(screen.queryByText("NOTE")).not.toBeInTheDocument();
  });
});
