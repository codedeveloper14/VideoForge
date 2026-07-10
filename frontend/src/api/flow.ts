import { api } from "./client";

export interface FlowAccount {
  name?: string;
  logged_in?: boolean;
}

export interface FlowAccountsResult {
  accounts?: FlowAccount[];
}

export interface FlowChromiumProfile {
  status?: string;
  active?: boolean;
}

export interface FlowChromiumStatusResult {
  profiles?: FlowChromiumProfile[];
}

export interface FlowStatus {
  since?: number;
  log?: string[];
  done?: number;
  total?: number;
  label?: string;
  running?: boolean;
}

export interface FlowImagesResult {
  images?: string[];
}

export interface FlowRunPromptsParams {
  prompts: string[];
  output_dir?: string;
  slots?: number;
  aspect_ratio?: string;
  model?: string;
  max_retries?: number;
  reference_image?: string;
  auto_open?: boolean;
}

export interface FlowRetryParams {
  output_dir: string;
  index: number;
  filename: string;
  fallback_prompts: string[];
}

export function flowAccounts() {
  return api.get<FlowAccountsResult>("/flow/accounts").then((r) => r.data);
}

export function flowLogin(account: number) {
  return api.post<{ ok: boolean }>("/flow/login", { account }).then((r) => r.data);
}

export function flowSaveCookie(account: number, cookie: string) {
  return api
    .post<{ ok: boolean }>("/flow/save-cookie", { account, cookie })
    .then((r) => r.data);
}

export function flowBridgeStatus() {
  return api.get<{ ok: boolean }>("/flow/bridge-status").then((r) => r.data);
}

export function flowChromiumStatus() {
  return api.get<FlowChromiumStatusResult>("/flow/chromium-status").then((r) => r.data);
}

export function flowOpenAll() {
  return api.post<{ ok: boolean }>("/flow/open-all").then((r) => r.data);
}

export function flowResetChromium() {
  return api.post<{ ok: boolean }>("/flow/reset-chromium").then((r) => r.data);
}

export function flowResetChromiumProfile(idx: number) {
  return api
    .post<{ ok: boolean }>("/flow/reset-chromium-profile", { idx })
    .then((r) => r.data);
}

export function flowRunPrompts({
  prompts,
  output_dir = "",
  slots = 2,
  aspect_ratio = "IMAGE_ASPECT_RATIO_LANDSCAPE",
  model = "NANO_BANANA_2",
  max_retries = 2,
  reference_image,
  auto_open,
}: FlowRunPromptsParams) {
  const body: Record<string, unknown> = {
    prompts,
    output_dir,
    slots,
    aspect_ratio,
    model,
    max_retries,
  };
  if (reference_image !== undefined) body.reference_image = reference_image;
  if (auto_open !== undefined) body.auto_open = auto_open;
  return api.post<{ ok: boolean }>("/flow/run-prompts", body).then((r) => r.data);
}

export function flowStop() {
  return api.post<{ ok: boolean }>("/flow/stop").then((r) => r.data);
}

export function flowRetry({ output_dir, index, filename, fallback_prompts }: FlowRetryParams) {
  return api
    .post<{ ok: boolean }>("/flow/retry", { output_dir, index, filename, fallback_prompts })
    .then((r) => r.data);
}

export function flowStatus(since?: number) {
  return api
    .get<FlowStatus>("/flow/status", { params: since ? { since } : {} })
    .then((r) => r.data);
}

export function flowFullLog() {
  return api.get<string>("/flow/full-log", { responseType: "text" }).then((r) => r.data);
}

export function flowImages(dir: string) {
  return api.get<FlowImagesResult>("/flow/images", { params: { dir } }).then((r) => r.data);
}

export function flowImageUrl(dir: string, file: string) {
  return `/api/flow/image?dir=${encodeURIComponent(dir)}&file=${encodeURIComponent(file)}`;
}

export function flowMtime(dir: string, file: string) {
  return api.get<{ mtime: number }>("/flow/mtime", { params: { dir, file } }).then((r) => r.data);
}

export function flowAbrirCarpeta() {
  return api.post<{ ok: boolean }>("/flow/abrir_carpeta").then((r) => r.data);
}
