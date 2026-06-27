/**
 * client/src/tests/unit/use_objects_query_params.test.tsx
 */

import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useObjectsQueryParams } from "@/hooks/use_objects_query_params";

function wrapper(initialEntries: string[]) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/objects" element={children} />
        </Routes>
      </MemoryRouter>
    );
  };
}

describe("useObjectsQueryParams", () => {
  it("reads projectId, drawingId, run, overlay from the URL", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15&overlay=42"]),
    });

    expect(result.current.projectId).toBe("2");
    expect(result.current.drawingId).toBe("8");
    expect(result.current.runId).toBe("15");
    expect(result.current.overlayId).toBe("42");
  });

  it("setDrawing updates projectId/drawingId and clears run+overlay", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15&overlay=42"]),
    });

    act(() => {
      result.current.setDrawing("3", "9");
    });

    expect(result.current.projectId).toBe("3");
    expect(result.current.drawingId).toBe("9");
    expect(result.current.runId).toBeUndefined();
    expect(result.current.overlayId).toBeUndefined();
  });

  it("setRun updates run and clears overlay, without touching projectId/drawingId", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&overlay=42"]),
    });

    act(() => {
      result.current.setRun("99");
    });

    expect(result.current.runId).toBe("99");
    expect(result.current.overlayId).toBeUndefined();
    expect(result.current.projectId).toBe("2");
    expect(result.current.drawingId).toBe("8");
  });

  it("setRun(null) removes the run param", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15"]),
    });

    act(() => {
      result.current.setRun(null);
    });

    expect(result.current.runId).toBeUndefined();
  });

  it("setRun leaves region focus untouched", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15&overlay=42&region=7"]),
    });

    act(() => {
      result.current.setRun("99");
    });

    expect(result.current.runId).toBe("99");
    expect(result.current.overlayId).toBeUndefined();
    expect(result.current.regionId).toBe("7");
  });

  it("setOverlay sets the overlay param without affecting run", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15"]),
    });

    act(() => {
      result.current.setOverlay("7");
    });

    expect(result.current.overlayId).toBe("7");
    expect(result.current.runId).toBe("15");
  });

  it("clearRunAndOverlay removes both params", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15&overlay=42"]),
    });

    act(() => {
      result.current.clearRunAndOverlay();
    });

    expect(result.current.runId).toBeUndefined();
    expect(result.current.overlayId).toBeUndefined();
    expect(result.current.projectId).toBe("2");
  });
});

describe("useObjectsQueryParams — regionId (PR5)", () => {
  it("reads regionId from the URL", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&region=7"]),
    });
    expect(result.current.regionId).toBe("7");
  });

  it("setRegion sets the region param without touching run or overlay", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15"]),
    });

    act(() => {
      result.current.setRegion("7");
    });

    expect(result.current.regionId).toBe("7");
    expect(result.current.runId).toBe("15");
  });

  it("setRegion(null) removes the region param", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&region=7"]),
    });

    act(() => {
      result.current.setRegion(null);
    });

    expect(result.current.regionId).toBeUndefined();
  });

  it("setDrawing clears regionId along with run and overlay", () => {
    const { result } = renderHook(() => useObjectsQueryParams(), {
      wrapper: wrapper(["/objects?projectId=2&drawingId=8&run=15&overlay=42&region=7"]),
    });

    act(() => {
      result.current.setDrawing("3", "9");
    });

    expect(result.current.regionId).toBeUndefined();
    expect(result.current.runId).toBeUndefined();
    expect(result.current.overlayId).toBeUndefined();
  });
});
