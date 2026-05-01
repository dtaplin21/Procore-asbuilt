/**
 * Split deployment: static SPA (e.g. Vercel) calls a separate API host (e.g. Render).
 * Set at build time: VITE_API_BASE_URL=https://api.example.com (no trailing slash).
 * Empty/ unset: same-origin + Vite dev proxy (`/api` → localhost:2000).
 */
const raw = import.meta.env.VITE_API_BASE_URL;

const trimmed =
  typeof raw === "string" ? raw.trim().replace(/\/+$/, "") : "";

export function apiUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return pathOrUrl;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/api") && trimmed !== "") {
    return `${trimmed}${pathOrUrl}`;
  }
  return pathOrUrl;
}
