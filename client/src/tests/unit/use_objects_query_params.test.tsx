import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ReactNode } from "react";

import { useObjectsQueryParams } from "@/hooks/use_objects_query_params";

function createWrapper(initialEntry: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/objects" element={children} />
        </Routes>
      </MemoryRouter>
    );
  };
}

describe("useObjectsQueryParams", () => {
  it("reads canonical params from the URL", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: createWrapper("/objects?projectId=2&drawingId=8&run=15&overlay=42"),
    });

    expect(result.current.projectId).toBe("2");
    expect(result.current.drawingId).toBe("8");
    expect(result.current.runId).toBe("15");
    expect(result.current.overlayId).toBe("42");
  });

  it("setDrawing replaces project/drawing and clears run and overlay", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: createWrapper("/objects?projectId=2&drawingId=8&run=15&overlay=42"),
    });

    act(() => {
      result.current.setDrawing("2", "9");
    });

    expect(result.current.projectId).toBe("2");
    expect(result.current.drawingId).toBe("9");
    expect(result.current.runId).toBeUndefined();
    expect(result.current.overlayId).toBeUndefined();
  });

  it("setRun clears overlay when run changes", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: createWrapper("/objects?projectId=2&drawingId=8&run=15&overlay=42"),
    });

    act(() => {
      result.current.setRun("16");
    });

    expect(result.current.runId).toBe("16");
    expect(result.current.overlayId).toBeUndefined();
  });

  it("setProject clears drawing, run, and overlay", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: createWrapper("/objects?projectId=2&drawingId=8&run=15&overlay=42"),
    });

    act(() => {
      result.current.setProject("3");
    });

    expect(result.current.projectId).toBe("3");
    expect(result.current.drawingId).toBeUndefined();
    expect(result.current.runId).toBeUndefined();
    expect(result.current.overlayId).toBeUndefined();
  });
});
