import { apiFetch, fetchCsrfToken, setStoredCsrfToken } from "./client";
import { IdentityResponse } from "../types/api";

export async function getCsrf(): Promise<string> {
  return fetchCsrfToken();
}

export async function register(username: string, email: string, password: string): Promise<IdentityResponse> {
  const data = await apiFetch<IdentityResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, email, password }),
  });
  return data;
}

export async function login(identifier: string, password: string): Promise<IdentityResponse> {
  const data = await apiFetch<IdentityResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ identifier, password }),
  });
  if (data.csrf_token) {
    setStoredCsrfToken(data.csrf_token);
  }
  return data;
}

export async function getMe(): Promise<IdentityResponse> {
  return apiFetch<IdentityResponse>("/api/v1/auth/me", {
    method: "GET",
  });
}

export async function logout(): Promise<{ logged_out: boolean }> {
  try {
    const res = await apiFetch<{ logged_out: boolean }>("/api/v1/auth/logout", {
      method: "POST",
    });
    setStoredCsrfToken(null);
    return res;
  } catch (err) {
    setStoredCsrfToken(null);
    throw err;
  }
}
