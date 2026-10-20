import { describe, expect, it } from "vitest";

import {
  hasActiveInspectionRun,
  isActiveInspectionRun,
  pickInspectionProgressRun,
  shouldPollInspectionRunProgress,
} from "@/lib/inspection-runs/active_run";

describe("isActiveInspectionRun", () => {
  it("treats processing runs as active", () => {
    expect(
      isActiveInspectionRun({ status: "processing", evidence_id: null }),
    ).toBe(true);
  });

  it("treats queued runs with evidence as active", () => {
    expect(isActiveInspectionRun({ status: "queued", evidence_id: 12 })).toBe(true);
  });

  it("does not treat deferred queued runs without evidence as active", () => {
    expect(isActiveInspectionRun({ status: "queued", evidence_id: null })).toBe(false);
  });

  it("does not treat failed or complete runs as active", () => {
    expect(isActiveInspectionRun({ status: "failed", evidence_id: 12 })).toBe(false);
    expect(isActiveInspectionRun({ status: "complete", evidence_id: 12 })).toBe(false);
  });
});

describe("hasActiveInspectionRun", () => {
  it("ignores orphaned deferred runs when another run is complete", () => {
    expect(
      hasActiveInspectionRun([
        { status: "complete", evidence_id: 5 },
        { status: "queued", evidence_id: null },
      ]),
    ).toBe(false);
  });

  it("blocks when a legacy queued run already has evidence linked", () => {
    expect(
      hasActiveInspectionRun([
        { status: "queued", evidence_id: 9 },
      ]),
    ).toBe(true);
  });
});

describe("shouldPollInspectionRunProgress", () => {
  it("polls while reindex/rematch mutation is pending for that run", () => {
    expect(
      shouldPollInspectionRunProgress(
        { id: 5, status: "complete", evidence_id: 1 },
        5,
      ),
    ).toBe(true);
  });
});

describe("pickInspectionProgressRun", () => {
  it("prefers selected run when it is inspecting", () => {
    const runs = [
      { id: 1, status: "processing", evidence_id: 10 },
      { id: 2, status: "complete", evidence_id: 11 },
    ] as const;
    expect(pickInspectionProgressRun([...runs], { selectedRunId: 1 })?.id).toBe(1);
  });

  it("falls back to any inspecting run when selection is complete", () => {
    const runs = [
      { id: 1, status: "complete", evidence_id: 10 },
      { id: 2, status: "processing", evidence_id: 11 },
    ] as const;
    expect(pickInspectionProgressRun([...runs], { selectedRunId: 1 })?.id).toBe(2);
  });
});
