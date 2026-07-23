import { api } from "./client";

export interface Doc {
  id: number;
  type: string;
  category: string;
  title: string;
  description: string;
  url: string;
  content: string;
  thumbnail_url: string;
  duration_label: string;
  tags: string;
  sort_order: number;
}

export interface PublicDocsResult {
  categories: Record<string, Doc[]>;
}

export interface HelpSubmitPayload {
  type?: string;
  category?: string;
  title: string;
  description?: string;
  email?: string;
}

export function listDocs() {
  return api.get<PublicDocsResult>("/docs").then((r) => r.data);
}

export function submitHelpRequest(payload: HelpSubmitPayload) {
  return api.post<{ ok: boolean }>("/help", payload).then((r) => r.data);
}
