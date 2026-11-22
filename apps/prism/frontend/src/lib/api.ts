import { readStorage, STORAGE_KEYS } from "./storage";

/** Error thrown for non-2xx API answers; `code` is the stable domain code (e.g. microsoft_reconnect_required). */
export class ApiError extends Error {
  code: string | null;
  status: number;
  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface ErrorPayload {
  detail?: unknown;
  code?: string;
}

/** FastAPI validation errors come back as `detail: [{msg, loc}]`; flatten them to readable text. */
function detailText(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    const parts = detail.map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)));
    return parts.join("; ");
  }
  return `Request failed (${status})`;
}

export function operatorHeaders(): Record<string, string> {
  const token = readStorage(STORAGE_KEYS.operatorToken);
  return token ? { "X-Manager-Operator-Token": token } : {};
}

/** Shared JSON fetch for every dashboard call. Resolves null for 204. */
export async function agentApi<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...operatorHeaders(), ...((options.headers as Record<string, string> | undefined) ?? {}) },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
    throw new ApiError(detailText(payload.detail, response.status), response.status, payload.code ?? null);
  }
  return (response.status === 204 ? null : await response.json()) as T;
}

export const jsonBody = (value: unknown): RequestInit => ({ body: JSON.stringify(value) });
export const errorMessage = (error: unknown): string => (error instanceof Error ? error.message : String(error));
