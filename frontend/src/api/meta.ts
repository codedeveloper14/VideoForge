import { api } from "./client";

export interface MetaAccount {
  name: string;
  active: boolean;
  user?: string;
}

export interface MetaSesionesResult {
  accounts?: MetaAccount[];
}

export interface MetaIniciarParams {
  project_name: string;
  prompt?: string;
  slots?: number;
  mode?: string;
  timeout?: number;
  images?: File[];
}

export interface MetaIniciarResult {
  project_dir?: string;
  project_name?: string;
  pid?: number | string;
}

export interface MetaLogResult {
  lines?: string[];
  next_offset?: number;
  finished?: boolean;
}

export interface MetaVideosResult {
  videos?: string[];
  done?: number;
  total?: number;
}

export interface MetaLaunchChromeParams {
  account?: string;
  slots?: number;
}

export interface MetaLaunchChromeResult {
  message?: string;
}

export interface MetaOpenDevmodeParams {
  account?: string;
}

export interface MetaOpenDevmodeResult {
  message?: string;
}

export function metaSesiones() {
  return api.get<MetaSesionesResult>("/meta/sesiones").then((r) => r.data);
}

export function metaLoginCuenta(account: string) {
  return api
    .post<{ ok: boolean }>("/meta/login_cuenta", { account })
    .then((r) => r.data);
}

export function metaBorrarSesion(account: string) {
  return api
    .post<{ ok: boolean }>("/meta/borrar_sesion", { account })
    .then((r) => r.data);
}

export function metaIniciar({
  project_name,
  prompt = "Cinematic slow zoom",
  slots = 1,
  mode = "ext",
  timeout = 900,
  images = [],
}: MetaIniciarParams) {
  const fd = new FormData();
  fd.append("project_name", project_name);
  fd.append("prompt", prompt);
  fd.append("slots", String(slots));
  fd.append("mode", mode);
  fd.append("timeout", String(timeout));
  images.forEach((file, i) => fd.append(`imagen_${i}`, file, file.name));
  return api.post<MetaIniciarResult>("/meta/iniciar", fd).then((r) => r.data);
}

export function metaDetener() {
  return api.post<{ ok: boolean }>("/meta/detener").then((r) => r.data);
}

export function metaLog(offset = 0) {
  return api
    .get<MetaLogResult>("/meta/log", { params: { offset } })
    .then((r) => r.data);
}

export function metaVideos(project: string) {
  return api
    .get<MetaVideosResult>("/meta/videos", { params: { project } })
    .then((r) => r.data);
}

export function metaVideoUrl(project: string, file: string, dl = 0) {
  const params = new URLSearchParams({ project, file, dl: String(dl) });
  return `/api/meta/video?${params.toString()}`;
}

export function metaDescargarTodasUrl(project: string) {
  const params = new URLSearchParams({ project });
  return `/api/meta/descargar_todas?${params.toString()}`;
}

export function metaAbrirCarpeta(project: string) {
  return api
    .post<{ ok: boolean }>("/meta/abrir_carpeta", { project })
    .then((r) => r.data);
}

export function metaLaunchChrome({
  account = "cuenta1",
  slots = 3,
}: MetaLaunchChromeParams = {}) {
  return api
    .post<MetaLaunchChromeResult>("/meta/launch_chrome", { account, slots })
    .then((r) => r.data);
}

export function metaOpenDevmode({ account = "cuenta1" }: MetaOpenDevmodeParams = {}) {
  return api
    .post<MetaOpenDevmodeResult>("/meta/open_devmode", { account })
    .then((r) => r.data);
}
