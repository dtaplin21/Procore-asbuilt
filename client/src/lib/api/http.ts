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

export async function readApiError(response: Response): Promise<never> {
  let message = `Request failed with status ${response.status}`;

  try {
    const data = (await response.json()) as {
      detail?: string | { message?: string };
    };

    if (typeof data?.detail === "string" && data.detail.trim()) {
      message = data.detail;
    } else if (
      data?.detail &&
      typeof data.detail === "object" &&
      typeof data.detail.message === "string" &&
      data.detail.message.trim()
    ) {
      message = data.detail.message;
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
