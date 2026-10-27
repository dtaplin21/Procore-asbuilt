import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkupWorkspace } from "./MarkupWorkspace";

const env = (globalThis as unknown as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const base = env.E2E_URL;
const drawingId = Number(env.E2E_DRAWING_ID ?? 1722);
const page = Number(env.E2E_PAGE ?? 99);
const fire = (el: Element, type: string, x: number, y: number) =>
  act(() => { el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y })); });

describe.skipIf(!base)("MarkupWorkspace against the real API", () => {
  it("draws, saves, filters by inspection type, changes status, deletes", async () => {
    render(<MarkupWorkspace drawingId={drawingId} page={page} pageImageUrl="data:image/gif;base64,R0lGODlhAQABAAAAACw=" pageAspect={1.4} api={{ baseUrl: base, userName: "Dom" }} />);
    await screen.findByText("No markups on this page yet.");

    const layer = screen.getByTestId("markup-layer");
    layer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON() {} }) as DOMRect;
    fireEvent.click(screen.getByRole("button", { name: "polyline" }));
    fireEvent.change(screen.getByLabelText("Inspection type"), { target: { value: "Underground Piping" } });
    fire(layer, "pointerdown", 260, 395);
    fire(layer, "pointerdown", 350, 405);
    fireEvent.keyDown(window, { key: "Enter" });

    const filter = await screen.findByText("Underground Piping");
    expect(filter).toBeTruthy();
    const res = await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`);
    const rows = await res.json();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "polyline", inspectionType: "Underground Piping", status: "Open", createdBy: "Dom", points: [[0.26, 0.79], [0.35, 0.81]] });

    fireEvent.click(screen.getByRole("button", { name: "select" }));
    fire(layer, "pointerdown", 300, 400);
    const panel = await screen.findByLabelText("Selected markup");
    fireEvent.change(within(panel).getByLabelText("Selected status"), { target: { value: "Closed" } });
    await waitFor(async () => expect((await (await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`)).json())[0].status).toBe("Closed"));
    fireEvent.click(within(panel).getByRole("button", { name: "Delete" }));
    await screen.findByText("No markups on this page yet.");
    expect(await (await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`)).json()).toEqual([]);
  });
});
