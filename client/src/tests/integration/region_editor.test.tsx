/**
 * client/src/tests/integration/region_editor.test.tsx
 *
 * RegionEditor through the real drawing_regions API client + fetch (not module mocks).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegionEditor } from "@/components/drawing-workspace/region_editor";

const PROJECT_ID = 3;
const MASTER_DRAWING_ID = 42;

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(body === null ? null : JSON.stringify(body), {
      status,
      headers: body === null ? undefined : { "Content-Type": "application/json" },
    }),
  );
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function mockBoundingClientRect(element: Element, rect: Partial<DOMRect> = {}) {
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 1000,
    bottom: 1000,
    width: 1000,
    height: 1000,
    toJSON: () => ({}),
    ...rect,
  } as DOMRect);
}

function renderRegionEditor(fetchMock: ReturnType<typeof vi.fn>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const view = render(
    <QueryClientProvider client={queryClient}>
      <RegionEditor
        projectId={PROJECT_ID}
        masterDrawingId={MASTER_DRAWING_ID}
        imageUrl="/sheet.png"
        pageWidth={1000}
        pageHeight={1000}
      />
    </QueryClientProvider>,
  );

  return { ...view, fetchMock };
}

describe("RegionEditor integration", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("draws a rect, fills tags, and creates the region via the API", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const method = init?.method ?? "GET";

      if (url.includes(`/drawings/${MASTER_DRAWING_ID}/regions`) && method === "GET") {
        return jsonResponse([]);
      }

      if (url.includes(`/drawings/${MASTER_DRAWING_ID}/regions`) && method === "POST") {
        const body = JSON.parse(init!.body as string);
        return jsonResponse(
          {
            id: 10,
            master_drawing_id: MASTER_DRAWING_ID,
            label: body.label,
            page: 1,
            geometry: body.geometry,
            inspection_type_tags: body.inspection_type_tags,
            location_tags: body.location_tags,
            created_at: "2026-06-24T00:00:00Z",
            updated_at: "2026-06-24T00:00:00Z",
          },
          201,
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });

    renderRegionEditor(fetchMock);

    await waitFor(() =>
      expect(screen.getByTestId("region-editor-existing-list")).toBeInTheDocument(),
    );

    const surface = screen.getByTestId("region-draw-surface");
    mockBoundingClientRect(surface);

    fireEvent.mouseDown(surface, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(surface, { clientX: 300, clientY: 300 });
    fireEvent.mouseUp(surface, { clientX: 300, clientY: 300 });

    expect(await screen.findByTestId("region-tag-form")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("region-inspection-types-input"), {
      target: { value: "Final" },
    });
    fireEvent.change(screen.getByTestId("region-locations-input"), {
      target: { value: "Roof" },
    });
    fireEvent.click(screen.getByTestId("region-tag-form-save"));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(postCall).toBeDefined();
    });

    const [, postInit] = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    const sentBody = JSON.parse(postInit!.body as string);
    expect(sentBody.inspection_type_tags).toEqual(["Final"]);
    expect(sentBody.location_tags).toEqual(["Roof"]);
    expect(sentBody.geometry.width).toBeCloseTo(0.2);
    expect(sentBody.geometry.height).toBeCloseTo(0.2);
  });

  it("cancelling the tag form returns to the draw canvas without saving", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const method = init?.method ?? "GET";
      if (url.includes(`/drawings/${MASTER_DRAWING_ID}/regions`) && method === "GET") {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });

    renderRegionEditor(fetchMock);

    await waitFor(() =>
      expect(screen.getByTestId("region-editor-existing-list")).toBeInTheDocument(),
    );

    const surface = screen.getByTestId("region-draw-surface");
    mockBoundingClientRect(surface);
    fireEvent.mouseDown(surface, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(surface, { clientX: 300, clientY: 300 });
    fireEvent.mouseUp(surface, { clientX: 300, clientY: 300 });

    expect(await screen.findByTestId("region-tag-form")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("region-tag-form-cancel"));

    expect(screen.getByTestId("region-draw-canvas")).toBeInTheDocument();
    expect(screen.queryByTestId("region-tag-form")).not.toBeInTheDocument();

    const postCalls = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(postCalls).toHaveLength(0);
  });

  it("renders existing regions and deletes one on click", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const method = init?.method ?? "GET";

      if (url.includes(`/drawings/${MASTER_DRAWING_ID}/regions`) && method === "GET") {
        return jsonResponse([
          {
            id: 7,
            master_drawing_id: MASTER_DRAWING_ID,
            label: "Roof",
            page: 1,
            geometry: { type: "rect", x: 0.01, y: 0.02, width: 0.05, height: 0.06 },
            inspection_type_tags: ["Final"],
            location_tags: ["Roof"],
            created_at: "2026-06-24T00:00:00Z",
            updated_at: "2026-06-24T00:00:00Z",
          },
        ]);
      }

      if (url.endsWith("/regions/7") && method === "DELETE") {
        return jsonResponse(null, 204);
      }

      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });

    renderRegionEditor(fetchMock);

    expect(await screen.findByText(/Roof — Final/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("region-editor-delete-7"));

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE");
      expect(deleteCall).toBeDefined();
      expect(requestUrl(deleteCall![0])).toContain(
        `/api/projects/${PROJECT_ID}/drawings/${MASTER_DRAWING_ID}/regions/7`,
      );
    });
  });
});
