const TIMEOUT_MS = 10_000;

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

function baseUrl(): string {
  const raw = required("DOMINION_PUBLISHER_BASE_URL").replace(/\/$/, "");
  const parsed = new URL(raw);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") throw new Error("DOMINION_PUBLISHER_BASE_URL must be http(s)");
  return raw;
}

export class PublisherError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) { super(detail); this.status = status; this.detail = detail; }
}

export async function publisherRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Operator-Token": required("DOMINION_PUBLISHER_OPERATOR_TOKEN"),
        ...(init.headers || {})
      },
      cache: "no-store"
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : { detail: await response.text() };
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : `publisher request failed (${response.status})`;
      throw new PublisherError(response.status, detail.slice(0, 400));
    }
    return payload as T;
  } catch (error) {
    if (error instanceof PublisherError) throw error;
    throw new PublisherError(503, error instanceof Error && error.name === "AbortError" ? "publisher request timed out" : "publisher is unreachable");
  } finally { clearTimeout(timer); }
}

export function apiError(error: unknown): { status: number; body: { error: string; detail: string } } {
  if (error instanceof PublisherError) return { status: error.status >= 400 && error.status < 600 ? error.status : 502, body: { error: "publisher_error", detail: error.detail } };
  return { status: 500, body: { error: "internal_error", detail: "unexpected server error" } };
}
