/**
 * MK OS API Client
 * =================
 * Thin wrapper around fetch with session handling,
 * error normalization, and JSON parsing.
 */

import { API_BASE } from "./constants";

export class ApiError extends Error {
  status: number;
  statusText: string;
  body?: unknown;

  constructor(status: number, statusText: string, body?: unknown) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

/**
 * Make an authenticated API request.
 * Automatically serializes body to JSON, includes credentials,
 * and handles error responses.
 */
async function request<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, headers: customHeaders, ...rest } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((customHeaders as Record<string, string>) || {}),
  };

  const config: RequestInit = {
    credentials: "include",
    headers,
    ...rest,
  };

  if (body !== undefined) {
    config.body = JSON.stringify(body);
  }

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, config);

  if (!response.ok) {
    let errorBody: unknown;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = await response.text();
    }

    // If unauthorized, redirect to login
    if (response.status === 401) {
      window.location.href = "/login";
    }

    throw new ApiError(response.status, response.statusText, errorBody);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/** GET request */
export function get<T>(endpoint: string): Promise<T> {
  return request<T>(endpoint, { method: "GET" });
}

/** POST request */
export function post<T>(endpoint: string, body?: unknown): Promise<T> {
  return request<T>(endpoint, { method: "POST", body });
}

/** PUT request */
export function put<T>(endpoint: string, body?: unknown): Promise<T> {
  return request<T>(endpoint, { method: "PUT", body });
}

/** DELETE request */
export function del<T>(endpoint: string): Promise<T> {
  return request<T>(endpoint, { method: "DELETE" });
}

/**
 * SWR-compatible fetcher function.
 * Use with: useSWR('/endpoint', fetcher)
 */
export const fetcher = <T>(endpoint: string): Promise<T> => get<T>(endpoint);
