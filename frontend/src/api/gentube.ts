import { api } from "./client";

export interface GentubeProfile {
  name?: string;
  logged_in?: boolean;
}

export interface GentubeCheckLoginResult {
  profiles?: GentubeProfile[];
}

export interface GentubeStatus {
  running?: boolean;
  log?: string[];
  total?: number;
  processed?: number;
  images?: number;
  rate?: string | number;
}

export interface GentubeImagesResult {
  images?: string[];
}

export interface GentubeRunPromptsParams {
  prompts: string[];
  slots?: number;
  repeat?: number;
  output_dir?: string;
  ratio?: string;
  quality?: string;
}

export function gentubeStatus() {
  return api.get<GentubeStatus>("/gentube/status").then((r) => r.data);
}

export function gentubeCheckLogin() {
  return api.get<GentubeCheckLoginResult>("/gentube/check-login").then((r) => r.data);
}

export function gentubeLogin(
  { profile = 0, cookie = "" }: { profile?: number; cookie?: string } = {},
) {
  return api
    .post<{ ok: boolean }>("/gentube/login", { profile, cookie })
    .then((r) => r.data);
}

export function gentubeRunPrompts({
  prompts,
  slots = 1,
  repeat = 1,
  output_dir = "",
  ratio = "1:1",
  quality = "standard",
}: GentubeRunPromptsParams) {
  return api
    .post<{ ok: boolean }>("/gentube/run-prompts", {
      prompts,
      slots,
      repeat,
      output_dir,
      ratio,
      quality,
    })
    .then((r) => r.data);
}

export function gentubeStop() {
  return api.post<{ ok: boolean }>("/gentube/stop").then((r) => r.data);
}

export function gentubeReset() {
  return api.post<{ ok: boolean }>("/gentube/reset").then((r) => r.data);
}

export function gentubeImages() {
  return api.get<string[] | GentubeImagesResult>("/gentube/images").then((r) => r.data);
}

export function gentubeImageUrl(name: string) {
  return `/api/gentube/image/${encodeURIComponent(name)}`;
}

export function gentubeClearImages() {
  return api.post<{ ok: boolean }>("/gentube/clear-images").then((r) => r.data);
}
