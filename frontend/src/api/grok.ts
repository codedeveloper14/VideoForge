import { api } from "./client";

export interface GrokAccount {
  name: string;
  active: boolean;
  user?: string;
}

export interface GrokSesionesResult {
  accounts?: GrokAccount[];
}

export interface GrokIniciarParams {
  project_name: string;
  prompt?: string;
  slots?: number;
  aspect_ratio?: string;
  video_length?: number;
  resolution?: string;
  images?: File[];
}

export interface GrokIniciarResult {
  project_dir?: string;
  project_name?: string;
  pid?: number | string;
}

export interface GrokRegenerarParams {
  video_name: string;
  project_name: string;
  prompt?: string;
  [key: string]: unknown;
}

export interface GrokRegenerarResult {
  ok: boolean;
  error?: string;
}

export interface GrokLogResult {
  lines?: string[];
  next_offset?: number;
  finished?: boolean;
}

export interface GrokVideosResult {
  videos?: string[];
  done?: number;
  total?: number;
}

export function grokSesiones() {
  return api.get<GrokSesionesResult>("/grok/sesiones").then((r) => r.data);
}

export function grokLoginCuenta(account: string) {
  return api
    .post<{ ok: boolean }>("/grok/login_cuenta", { account })
    .then((r) => r.data);
}

export function grokBorrarSesion(account: string) {
  return api
    .post<{ ok: boolean }>("/grok/borrar_sesion", { account })
    .then((r) => r.data);
}

export function grokIniciar({
  project_name,
  prompt = "Cinematic slow zoom",
  slots = 3,
  aspect_ratio = "2:3",
  video_length = 6,
  resolution = "480p",
  images = [],
}: GrokIniciarParams) {
  const fd = new FormData();
  fd.append("project_name", project_name);
  fd.append("prompt", prompt);
  fd.append("slots", String(slots));
  fd.append("aspect_ratio", aspect_ratio);
  fd.append("video_length", String(video_length));
  fd.append("resolution", resolution);
  images.forEach((file, i) => fd.append(`imagen_${i}`, file, file.name));
  return api.post<GrokIniciarResult>("/grok/iniciar", fd).then((r) => r.data);
}

export function grokRegenerar(params: GrokRegenerarParams) {
  return api
    .post<GrokRegenerarResult>("/grok/regenerar", params)
    .then((r) => r.data);
}

export function grokDetener(project = "") {
  return api
    .post<{ ok: boolean }>("/grok/detener", { project })
    .then((r) => r.data);
}

export function grokLog(offset = 0, project = "") {
  return api
    .get<GrokLogResult>("/grok/log", { params: { offset, project } })
    .then((r) => r.data);
}

export function grokVideos(project: string) {
  return api
    .get<GrokVideosResult>("/grok/videos", { params: { project } })
    .then((r) => r.data);
}

export function grokVideoUrl(project: string, file: string, dl = 0) {
  const params = new URLSearchParams({ project, file, dl: String(dl) });
  return `/api/grok/video?${params.toString()}`;
}

export function grokDescargarTodasUrl(project: string) {
  const params = new URLSearchParams({ project });
  return `/api/grok/descargar_todas?${params.toString()}`;
}

export function grokAbrirCarpeta(project: string) {
  return api
    .post<{ ok: boolean }>("/grok/abrir_carpeta", { project })
    .then((r) => r.data);
}
