import { api } from "./client";

export interface AdminDoc {
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
  is_published: boolean;
  created_at: string;
  created_by: string;
}

export interface AdminDocInput {
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
  is_published: boolean;
}

export function listAdminDocs() {
  return api.get<AdminDoc[]>("/admin/docs").then((r) => r.data);
}

export function createAdminDoc(data: AdminDocInput) {
  return api.post<{ id: number }>("/admin/docs", data).then((r) => r.data);
}

export function updateAdminDoc(id: number, data: AdminDocInput) {
  return api.put<{ ok: boolean }>(`/admin/docs/${id}`, data).then((r) => r.data);
}

export function deleteAdminDoc(id: number) {
  return api.delete<{ ok: boolean }>(`/admin/docs/${id}`).then((r) => r.data);
}
