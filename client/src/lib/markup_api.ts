import type { DrawingMarkup, MarkupSummaryRow, NewMarkup, Pt } from "../types/drawing_markup";

export interface ApiOptions {
  baseUrl?: string;
  /** Name sent as X-Procore-User. The server stores it as created_by. */
  userName?: string;
  fetchImpl?: typeof fetch;
}

export class MarkupApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(opts: ApiOptions, path: string, init: RequestInit = {}): Promise<T> {
  const f = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.userName) headers["X-Procore-User"] = opts.userName;
  const res = await f(`${opts.baseUrl ?? ""}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new MarkupApiError(res.status, typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`);
  return body as T;
}

export const listMarkups = (o: ApiOptions, drawingId: number, page?: number) =>
  call<DrawingMarkup[]>(o, `/api/drawings/${drawingId}/markups${page ? `?page=${page}` : ""}`);

export const markupSummary = (o: ApiOptions, drawingId: number, page?: number) =>
  call<MarkupSummaryRow[]>(o, `/api/drawings/${drawingId}/markups/summary${page ? `?page=${page}` : ""}`);

export const createMarkup = (o: ApiOptions, drawingId: number, body: NewMarkup) =>
  call<DrawingMarkup>(o, `/api/drawings/${drawingId}/markups`, {
    method: "POST",
    body: JSON.stringify({
      page: body.page, kind: body.kind, points: body.points, label: body.label ?? null,
      inspection_type: body.inspectionType ?? null, status: body.status ?? null, color: body.color ?? null,
    }),
  });

export const patchMarkup = (
  o: ApiOptions, id: number,
  changes: { points?: Pt[]; label?: string | null; inspectionType?: string | null; status?: string | null; color?: string | null },
) => {
  const body: Record<string, unknown> = {};
  if (changes.points !== undefined) body.points = changes.points;
  if (changes.label !== undefined) body.label = changes.label;
  if (changes.inspectionType !== undefined) body.inspection_type = changes.inspectionType;
  if (changes.status !== undefined) body.status = changes.status;
  if (changes.color !== undefined) body.color = changes.color;
  return call<DrawingMarkup>(o, `/api/markups/${id}`, { method: "PATCH", body: JSON.stringify(body) });
};

export const deleteMarkup = (o: ApiOptions, id: number) => call<void>(o, `/api/markups/${id}`, { method: "DELETE" });
