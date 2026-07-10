import { api } from "./client";

// ── Whisk ──────────────────────────────────────────────────────────
export interface WhiskProfile {
  name?: string;
  logged_in?: boolean;
  active?: boolean;
}

export interface WhiskCheckLoginResult {
  profiles?: WhiskProfile[];
}

export interface WhiskStatus {
  running?: boolean;
  log?: string[];
  total?: number;
  processed?: number;
  images?: number;
  rate?: string | number;
}

export interface WhiskImagesResult {
  images?: string[];
}

export interface WhiskRunPromptsParams {
  prompts: string;
  slots?: number;
  repeat?: number;
  output_dir?: string;
}

export function whiskStatus() {
  return api.get<WhiskStatus>("/whisk/status").then((r) => r.data);
}

export function whiskLogin(
  { profile = 0, account_id = 0, cookie = "" }: { profile?: number; account_id?: number; cookie?: string } = {},
) {
  return api
    .post<{ ok: boolean }>("/whisk/login", { profile, account_id, cookie })
    .then((r) => r.data);
}

export function whiskCheckLogin() {
  return api.get<WhiskCheckLoginResult>("/whisk/check-login").then((r) => r.data);
}

export function whiskSetSubjectFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return api
    .post<{ ok: boolean }>("/whisk/set-subject", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
}

export function whiskSetSubjectBase64(image: string, ext = "jpg") {
  return api
    .post<{ ok: boolean }>("/whisk/set-subject", { image, ext })
    .then((r) => r.data);
}

export function whiskClearSubject() {
  return api.delete<{ ok: boolean }>("/whisk/set-subject").then((r) => r.data);
}

export function whiskRunPrompts({ prompts, slots = 1, repeat = 1, output_dir = "" }: WhiskRunPromptsParams) {
  return api
    .post<{ ok: boolean }>("/whisk/run-prompts", { prompts, slots, repeat, output_dir })
    .then((r) => r.data);
}

export function whiskStop() {
  return api.post<{ ok: boolean }>("/whisk/stop").then((r) => r.data);
}

export function whiskImages() {
  return api.get<string[] | WhiskImagesResult>("/whisk/images").then((r) => r.data);
}

export function whiskImageUrl(name: string) {
  return `/api/whisk/image/${encodeURIComponent(name)}`;
}

export function whiskClearImages() {
  return api.post<{ ok: boolean }>("/whisk/clear-images").then((r) => r.data);
}

export function whiskAbrirCarpeta() {
  return api.post<{ ok: boolean }>("/whisk/abrir_carpeta").then((r) => r.data);
}

// ── Pollination (lives here per one-endpoint convention) ────────────
export interface PollinationGenerateParams {
  prompts: string;
  ratio?: string;
  width?: number;
  height?: number;
  output_dir?: string;
}

export interface PollinationGenerateResult {
  images?: string[];
  files?: string[];
  urls?: Record<string, string>;
}

export function pollinationGenerate({
  prompts,
  ratio = "16:9",
  width = 1920,
  height = 1097,
  output_dir = "",
}: PollinationGenerateParams) {
  return api
    .post<PollinationGenerateResult>("/pollination/generate", {
      prompts,
      ratio,
      width,
      height,
      output_dir,
    })
    .then((r) => r.data);
}
