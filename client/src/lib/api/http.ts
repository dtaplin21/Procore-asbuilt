/**
 * Shared fetch helpers for `client/src/lib/api/*` modules.
 * JSON requests set default Content-Type; multipart uploads must not (see `uploadProjectDrawing` in drawings.ts).
 */

export async function parseJsonSafe(response: Response) {
  const contentType = response.headers.get("content-type");

  if (contentType?.includes("application/json")) {
    return response.json();
  }

  return null;
}

/** FastAPI may send `detail` as a string, object, or validation error array. */
function messageFromFastApiDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const msg = (first as { msg?: string }).msg;
      if (typeof msg === "string" && msg.trim()) {
        return msg.trim();
      }
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return "Validation error";
    }
  }

  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { message?: string }).message === "string" &&
    (detail as { message: string }).message.trim()
  ) {
    return (detail as { message: string }).message.trim();
  }

  return null;
}

export async function readApiError(response: Response): Promise<never> {
  let message = `Request failed with status ${response.status}`;

  try {
    const data = (await response.json()) as {
      detail?: unknown;
      message?: string;
    };

    const fromDetail = messageFromFastApiDetail(data?.detail);
    if (fromDetail) {
      message = fromDetail;
    } else if (typeof data?.message === "string" && data.message.trim()) {
      message = data.message.trim();
    }
  } catch {
    if (response.statusText) {
      message = response.statusText;
    }
  }

  throw new Error(message);
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    await readApiError(response);
  }

  const data = await parseJsonSafe(response);
  return data as T;
}
