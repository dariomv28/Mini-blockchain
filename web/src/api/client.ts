import { ApiErrorPayload } from "../types/api";

export class ApiClientError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

let cachedCsrfToken: string | null = null;

export function setStoredCsrfToken(token: string | null) {
  cachedCsrfToken = token;
}

export function getStoredCsrfToken(): string | null {
  return cachedCsrfToken;
}

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

function notifyUnauthorized() {
  for (const listener of unauthorizedListeners) {
    try {
      listener();
    } catch {
      // Ignore listener error
    }
  }
}

export async function fetchCsrfToken(): Promise<string> {
  const res = await fetch("/api/v1/auth/csrf", {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new ApiClientError(res.status, "CSRF_FETCH_FAILED", "Failed to fetch CSRF token");
  }

  const data = await res.json();
  cachedCsrfToken = data.csrf_token;
  return data.csrf_token;
}

function extractErrorInfo(payload: any, defaultStatus: number): { code: string; message: string } {
  let code = "UNKNOWN_ERROR";
  let message = `HTTP Error ${defaultStatus}`;

  if (payload && typeof payload === "object") {
    if (payload.error && typeof payload.error === "object") {
      code = payload.error.code || code;
      message = payload.error.message || message;
    } else if (payload.detail) {
      if (typeof payload.detail === "object") {
        code = payload.detail.error || payload.detail.code || code;
        message = payload.detail.message || message;
      } else if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    }
  }

  return { code, message };
}

interface RequestOptions extends RequestInit {
  idempotencyKey?: string;
}

export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const isMutation = ["POST", "PUT", "DELETE", "PATCH"].includes(method);

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (isMutation && options.body && typeof options.body === "string" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  if (isMutation) {
    if (!cachedCsrfToken) {
      try {
        await fetchCsrfToken();
      } catch {
        // If CSRF fetch fails here, server will reject with 403
      }
    }
    if (cachedCsrfToken) {
      headers["X-CSRF-Token"] = cachedCsrfToken;
    }
  }

  let res = await fetch(endpoint, {
    ...options,
    headers,
    credentials: "include",
  });

  // If CSRF failed on a mutation (403 with CSRF_FAILED or similar), refresh token and retry once
  if (isMutation && (res.status === 403 || res.status === 401)) {
    const errorClone = res.clone();
    try {
      const errorJson: ApiErrorPayload = await errorClone.json();
      const { code, message } = extractErrorInfo(errorJson, res.status);
      const isCsrfError =
        (code === "CSRF_FAILED" && message !== "Invalid request origin") ||
        code === "INVALID_CSRF_TOKEN" ||
        code === "MISSING_CSRF_TOKEN" ||
        (message.toLowerCase().includes("csrf") && message !== "Invalid request origin");

      if (isCsrfError) {
        await fetchCsrfToken();
        if (cachedCsrfToken) {
          headers["X-CSRF-Token"] = cachedCsrfToken;
          res = await fetch(endpoint, {
            ...options,
            headers,
            credentials: "include",
          });
        }
      }
    } catch {
      // Ignore JSON parse error on retry check
    }
  }

  // Handle 401 session expiry across authenticated routes
  if (
    res.status === 401 &&
    !endpoint.includes("/auth/login") &&
    !endpoint.includes("/auth/csrf")
  ) {
    notifyUnauthorized();
  }

  if (!res.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = `HTTP Error ${res.status}`;

    try {
      const errorData: ApiErrorPayload = await res.json();
      const info = extractErrorInfo(errorData, res.status);
      errorCode = info.code;
      errorMessage = info.message;
    } catch {
      errorMessage = res.statusText || errorMessage;
    }

    throw new ApiClientError(res.status, errorCode, errorMessage);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json() as Promise<T>;
}
