import { api } from "./client";

export interface QwenAccount {
  name: string;
  active: boolean;
  user?: string;
}

export interface QwenSesionesResult {
  accounts?: QwenAccount[];
}

export interface QwenIniciarParams {
  project_name: string;
  prompt?: string;
  slots?: number;
  size?: string;
  timeout?: number;
  aspect_ratio?: string;
  images?: File[];
}

export interface QwenIniciarResult {
  project_dir?: string;
  project_name?: string;
  pid?: number | string;
}

export interface QwenRegenerarParams {
  project_name: string;
  video_name: string;
  prompt?: string;
  size?: string;
  [key: string]: unknown;
}

export interface QwenRegenerarResult {
  ok: boolean;
  error?: string;
}

export interface QwenLogResult {
  lines?: string[];
  next_offset?: number;
  finished?: boolean;
}

export interface QwenVideosResult {
  videos?: string[];
  done?: number;
  total?: number;
}

export function qwenSesiones() {
  return api.get<QwenSesionesResult>("/qwen/sesiones").then((r) => r.data);
}

export function qwenLoginCuenta(account: string) {
  return api
    .post<{ ok: boolean }>("/qwen/login_cuenta", { account })
    .then((r) => r.data);
}

export function qwenBorrarSesion(account: string) {
  return api
    .post<{ ok: boolean }>("/qwen/borrar_sesion", { account })
    .then((r) => r.data);
}

export function qwenIniciar({
  project_name,
  prompt = "Cinematic slow zoom",
  slots = 2,
  size = "1280x720",
  timeout = 900,
  aspect_ratio = "16:9",
  images = [],
}: QwenIniciarParams) {
  const fd = new FormData();
  fd.append("project_name", project_name);
  fd.append("prompt", prompt);
  fd.append("slots", String(slots));
  fd.append("size", size);
  fd.append("timeout", String(timeout));
  fd.append("aspect_ratio", aspect_ratio);
  images.forEach((file, i) => fd.append(`imagen_${i}`, file, file.name));
  return api.post<QwenIniciarResult>("/qwen/iniciar", fd).then((r) => r.data);
}

export function qwenRegenerar({
  project_name,
  video_name,
  prompt,
  size,
}: QwenRegenerarParams) {
  return api
    .post<QwenRegenerarResult>("/qwen/regenerar", {
      project_name,
      video_name,
      prompt,
      size,
    })
    .then((r) => r.data);
}

export function qwenDetener() {
  return api.post<{ ok: boolean }>("/qwen/detener").then((r) => r.data);
}

export function qwenLog(offset = 0) {
  return api
    .get<QwenLogResult>("/qwen/log", { params: { offset } })
    .then((r) => r.data);
}

export function qwenVideos(project: string) {
  return api
    .get<QwenVideosResult>("/qwen/videos", { params: { project } })
    .then((r) => r.data);
}

export function qwenVideoUrl(project: string, file: string, dl = 0) {
  const params = new URLSearchParams({ project, file, dl: String(dl) });
  return `/api/qwen/video?${params.toString()}`;
}

export function qwenDescargarTodasUrl(project: string) {
  const params = new URLSearchParams({ project });
  return `/api/qwen/descargar_todas?${params.toString()}`;
}

export function qwenAbrirCarpeta(project: string) {
  return api
    .post<{ ok: boolean }>("/qwen/abrir_carpeta", { project })
    .then((r) => r.data);
}
