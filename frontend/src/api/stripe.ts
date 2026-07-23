import { api } from "./client";

export interface CheckoutResult {
  url: string;
  fallback?: boolean;
}

export interface PollSessionResult {
  paid: boolean;
  plan?: string | null;
  error?: string;
}

export function startCheckout(plan: string) {
  return api
    .get<CheckoutResult>("/stripe/checkout", { params: { plan } })
    .then((r) => r.data);
}

export function pollSession(sessionId: string, plan?: string) {
  return api
    .get<PollSessionResult>("/stripe/poll-session", {
      params: { session_id: sessionId, plan },
    })
    .then((r) => r.data);
}
