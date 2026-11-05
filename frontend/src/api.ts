import type { ConverseResponse, Health, Product, Session } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // The body was not JSON.
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function getCatalog(): Promise<Product[]> {
  return request<Product[]>("/api/catalog");
}

export function createSession(): Promise<Session> {
  return request<Session>("/api/sessions", { method: "POST" });
}

export function sendMessage(
  sessionId: string,
  message: string,
  budgetCents: number | null,
): Promise<ConverseResponse> {
  return request<ConverseResponse>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message, budget_cents: budgetCents }),
  });
}

export function money(cents: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

export function dollarsToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const amount = Number(trimmed);
  if (!Number.isFinite(amount) || amount < 0) {
    return null;
  }
  return Math.round(amount * 100);
}
