import { api } from "./client";

export interface VibesAccount {
  name: string;
  active: boolean;
  user?: string;
}

export interface VibesSesionesResult {
  accounts?: VibesAccount[];
}

export interface VibesIniciarParams {
  project_name: string;
  prompt: string;
  slots?: number;
  timeout?: number;
  reference_image?: string;
  images?: File[];
}

export interface VibesIniciarResult {
  project_dir?: string;
  project_name?: string;
  pid?: number | string;
}

export interface VibesLogResult {
  lines?: string[];
  next_offset?: number;
  finished?: boolean;
}

export interface VibesVideosResult {
  videos?: string[];
  done?: number;
  total?: number;
}

export interface VibesLaunchChromeResult {
  message?: string;
}

export function vibesSesiones() {
  return api.get<VibesSesionesResult>("/vibes/sesiones").then((r) => r.data);
}

export function vibesLoginCuenta(account: string) {
  return api
    .post<{ ok: boolean }>("/vibes/login_cuenta", { account })
    .then((r) => r.data);
}

export function vibesBorrarSesion(account: string) {
  return api
    .post<{ ok: boolean }>("/vibes/borrar_sesion", { account })
    .then((r) => r.data);
}

export function vibesLaunchChrome() {
  return api.post<VibesLaunchChromeResult>("/vibes/launch_chrome").then((r) => r.data);
}

export function vibesIniciar({
  project_name,
  prompt,
  slots = 1,
  timeout = 300,
  reference_image,
  images = [],
}: VibesIniciarParams) {
  const fd = new FormData();
  fd.append("project_name", project_name);
  fd.append("prompt", prompt);
  fd.append("slots", String(slots));
  fd.append("timeout", String(timeout));
  if (reference_image) fd.append("reference_image", reference_image);
  images.forEach((file, i) => fd.append(`imagen_${i}`, file, file.name));
  return api.post<VibesIniciarResult>("/vibes/iniciar", fd).then((r) => r.data);
}

export function vibesDetener(project = "") {
  return api
    .post<{ ok: boolean }>("/vibes/detener", { project })
    .then((r) => r.data);
}

export function vibesLog(offset = 0, project = "") {
  return api
    .get<VibesLogResult>("/vibes/log", { params: { offset, project } })
    .then((r) => r.data);
}

export function vibesVideos(project: string) {
  return api
    .get<VibesVideosResult>("/vibes/videos", { params: { project } })
    .then((r) => r.data);
}

export function vibesVideoUrl(project: string, file: string, dl = 0) {
  const params = new URLSearchParams({ project, file, dl: String(dl) });
  return `/api/vibes/video?${params.toString()}`;
}

export function vibesDescargarTodasUrl(project: string) {
  const params = new URLSearchParams({ project });
  return `/api/vibes/descargar_todas?${params.toString()}`;
}

export function vibesAbrirCarpeta(project: string) {
  return api
    .post<{ ok: boolean }>("/vibes/abrir_carpeta", { project })
    .then((r) => r.data);
}
