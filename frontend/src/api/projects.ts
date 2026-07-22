import { api } from "./client";
import type { Project } from "../types";

export interface CreateProjectResult {
  ok: boolean;
  nombre: string;
  ruta: string;
}

export interface ProjectScene {
  index: string;
  image: string | null;
  video: string | null;
  has_video: boolean;
}

export interface ProjectContentDebug {
  img_dir: string;
  img_count: number;
  vid_count: number;
  img_dir_exists: boolean;
}

export interface ProjectContent {
  scenes: ProjectScene[];
  total: number;
  with_video: number;
  images_only: number;
  debug: ProjectContentDebug;
}

export function listProjects() {
  return api.get<Project[]>("/proyectos/listar").then((r) => r.data);
}

export function createProject(nombre: string) {
  return api
    .post<CreateProjectResult>("/proyectos/crear", { nombre })
    .then((r) => r.data);
}

export function deleteProject(nombre: string) {
  return api
    .post<{ ok: boolean; nombre: string; msg: string | null }>(
      "/proyectos/borrar",
      { nombre },
    )
    .then((r) => r.data);
}

export function getProjectContent(project: string) {
  return api
    .get<ProjectContent>("/proyectos/contenido", { params: { project } })
    .then((r) => r.data);
}

export function imagenFileUrl(project: string, file: string) {
  return `/api/proyectos/imagen_file?project=${encodeURIComponent(project)}&file=${encodeURIComponent(file)}`;
}

export function videoFileUrl(project: string, file: string) {
  return `/api/proyectos/video_file?project=${encodeURIComponent(project)}&file=${encodeURIComponent(file)}`;
}

export function uploadProjectImage(project: string, file: File) {
  const form = new FormData();
  form.append("project", project);
  form.append("file", file);
  return api
    .post<{ ok: boolean; file: string }>("/proyectos/subir_imagen", form)
    .then((r) => r.data);
}

export function uploadProjectVideo(project: string, file: File) {
  const form = new FormData();
  form.append("project", project);
  form.append("file", file);
  return api
    .post<{ ok: boolean; file: string }>("/proyectos/subir_video", form)
    .then((r) => r.data);
}

export function listFinalVideos(project: string) {
  return api
    .get<{ videos: string[] }>("/proyectos/videos_final", {
      params: { project },
    })
    .then((r) => r.data);
}

export function abrirVideoFinal(project: string) {
  return api
    .post<{ ok: boolean; path?: string; error?: string }>("/proyectos/abrir_video_final", { project })
    .then((r) => r.data);
}
